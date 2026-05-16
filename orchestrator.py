"""
Orchestrator (Step 7b — with plan modification support)
────────────────────────────────────────────────────────
Handles yes / no / modify during pending approval.
"""

import anthropic
from config.settings import CLAUDE_MODEL, DEBUG_VERBOSE
from agents.planner import run_planner
from agents.risk_monitor import run_risk_monitor
from memory.redis_store import StateStore
from memory.approval_gate import ApprovalGate

ORCHESTRATOR_SYSTEM_PROMPT = """You are the orchestrator for an AI-powered project management system.

You analyse each user message and decide which specialist agent to invoke.
You have access to these agents:
  - planner: Creates project milestones and tasks from a description
  - risk_monitor: Scans for overdue issues, stalled work, and at-risk projects

Your response must be a JSON object with this exact shape:
{
  "agent": "planner" | "risk_monitor" | "none",
  "request": "<reformulated request to send to the agent>",
  "project_id": "<project ID if mentioned, else null>",
  "reply_if_no_agent": "<conversational reply if agent is none>"
}

Rules:
- Use "planner" when the user wants to plan a project, create milestones, break down work, or build a roadmap.
- Use "risk_monitor" when the user asks about risks, blockers, overdue tasks, stalled work, project health, or wants a status scan.
- Use "none" for greetings, questions about the system, or anything outside PM scope.
- The "request" field should be a clean, complete instruction for the agent.
- Always set project_id if the user mentioned one.
- Never add commentary outside the JSON object.
"""

MODIFICATION_CLASSIFIER_PROMPT = """You are helping classify a user's response during a plan approval step.

The user was shown a proposed project plan and asked to confirm or modify it.
Classify their response into one of three categories:

- "confirm" — user wants to proceed (yes, ok, do it, looks good, go ahead, approve, etc.)
- "reject"  — user wants to cancel (no, cancel, stop, abort, never mind, etc.)
- "modify"  — user wants to change something (add, remove, change, update, instead, also, etc.)

Respond with ONLY a JSON object:
{
  "intent": "confirm" | "reject" | "modify",
  "modification_request": "<what they want changed, only if intent is modify, else null>"
}
"""


class Orchestrator:
    def __init__(self, session_id: str = "default"):
        self.client = anthropic.Anthropic()
        self.state = StateStore(session_id=session_id)
        self.gate = ApprovalGate(session_id=session_id)

    def handle(self, user_input: str) -> dict:
        # ── Check if user is responding to a pending approval ─────────────────
        if self.gate.has_pending():
            return self._handle_approval_response(user_input)

        self.state.add_message("user", user_input)

        # ── Route the request ─────────────────────────────────────────────────
        routing_response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=self.state.get_messages(),
        )

        raw = routing_response.content[0].text.strip()

        if DEBUG_VERBOSE:
            print(f"\n[Orchestrator] Routing: {raw}\n")

        try:
            routing = _parse_json(raw)
        except Exception:
            reply = "Sorry, I had trouble understanding that. Could you rephrase?"
            self.state.add_message("assistant", reply)
            return {"agent_used": None, "agent_output": None, "reply": reply}

        agent = routing.get("agent", "none")
        project_id = routing.get("project_id")

        if project_id and not self.state.get_project().project_id:
            self.state.set_project(project_id)

        # ── Planner ───────────────────────────────────────────────────────────
        if agent == "planner":
            return self._run_planner_with_approval(
                request=routing["request"],
                project_id=project_id or self.state.get_project().project_id,
            )

        # ── Risk Monitor ──────────────────────────────────────────────────────
        elif agent == "risk_monitor":
            print(f"\n[Orchestrator] → Risk Monitor")
            agent_output = run_risk_monitor(request=routing["request"])
            self.state.record_agent_output("risk_monitor", agent_output)
            reply = agent_output["summary"] or "Risk scan complete."
            self.state.add_message("assistant", reply)
            return {"agent_used": "risk_monitor", "agent_output": agent_output, "reply": reply}

        # ── No agent ──────────────────────────────────────────────────────────
        else:
            reply = routing.get("reply_if_no_agent", "How can I help with your project?")
            self.state.add_message("assistant", reply)
            return {"agent_used": None, "agent_output": None, "reply": reply}

    def _run_planner_with_approval(self, request: str, project_id: str | None = None) -> dict:
        """Run planner in dry-run mode and store result for approval."""
        print(f"\n[Orchestrator] → Planner (dry run)")
        agent_output = run_planner(
            request=request,
            project_id=project_id,
            dry_run=True,
        )

        milestones = agent_output.get("milestones", [])
        tasks = agent_output.get("tasks", [])

        if milestones or tasks:
            pending = {
                "request": request,
                "project_id": project_id,
                "proposed_milestones": milestones,
                "proposed_tasks": tasks,
            }
            self.gate.store_pending(pending)
            confirmation_prompt = self.gate.format_confirmation_prompt(pending)
            # Append a hint about modifications
            confirmation_prompt += "\n\nOr tell me what you'd like to change."
            self.state.add_message("assistant", confirmation_prompt)
            return {
                "agent_used": "planner",
                "agent_output": agent_output,
                "reply": confirmation_prompt,
                "awaiting_approval": True,
            }
        else:
            reply = agent_output["summary"] or "Here's the current plan."
            self.state.add_message("assistant", reply)
            return {"agent_used": "planner", "agent_output": agent_output, "reply": reply}

    def _handle_approval_response(self, user_input: str) -> dict:
        """Handle confirm / reject / modify during pending approval."""

        # Use Claude to classify the intent
        classification_response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=128,
            system=MODIFICATION_CLASSIFIER_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )

        try:
            classification = _parse_json(classification_response.content[0].text.strip())
            intent = classification.get("intent", "modify")
            modification = classification.get("modification_request")
        except Exception:
            intent = "modify"
            modification = user_input

        if DEBUG_VERBOSE:
            print(f"\n[Orchestrator] Approval intent: {intent}, modification: {modification}")

        # ── Confirm ───────────────────────────────────────────────────────────
        if intent == "confirm":
            pending = self.gate.get_pending()
            self.gate.clear_pending()

            print(f"\n[Orchestrator] ✅ Confirmed — executing plan")
            agent_output = run_planner(
                request=pending["request"],
                project_id=pending.get("project_id"),
                dry_run=False,
            )

            self.state.record_milestones(agent_output["milestones"])
            self.state.record_tasks(agent_output["tasks"])
            self.state.record_agent_output("planner", agent_output)

            reply = agent_output["summary"] or "Plan created in Linear."
            self.state.add_message("assistant", reply)
            return {
                "agent_used": "planner",
                "agent_output": agent_output,
                "reply": f"✅ Confirmed! {reply}",
            }

        # ── Reject ────────────────────────────────────────────────────────────
        elif intent == "reject":
            self.gate.clear_pending()
            reply = "Cancelled. Nothing was created in Linear. Let me know if you'd like to start over or adjust the plan."
            self.state.add_message("assistant", reply)
            return {"agent_used": None, "agent_output": None, "reply": reply}

        # ── Modify ────────────────────────────────────────────────────────────
        else:
            pending = self.gate.get_pending()
            original_request = pending.get("request", "")
            project_id = pending.get("project_id")

            # Build a revised request combining original + modification
            revised_request = (
                f"{original_request}\n\n"
                f"Modification requested by user: {modification or user_input}\n\n"
                f"Please update the plan accordingly. Keep what was already good, "
                f"apply the requested changes."
            )

            print(f"\n[Orchestrator] 🔄 Modifying plan: {modification or user_input}")

            # Clear old pending and re-run planner with revised request
            self.gate.clear_pending()
            return self._run_planner_with_approval(
                request=revised_request,
                project_id=project_id,
            )

    def get_state_snapshot(self) -> dict:
        return {
            **self.state.snapshot(),
            "awaiting_approval": self.gate.has_pending(),
        }


def _parse_json(text: str) -> dict:
    import json, re
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
