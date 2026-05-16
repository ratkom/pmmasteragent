"""
Orchestrator
────────────
Routes user requests to specialist agents and manages session state.
"""

import anthropic
from config.settings import CLAUDE_MODEL, DEBUG_VERBOSE
from agents.planner import run_planner
from agents.risk_monitor import run_risk_monitor
from memory.redis_store import StateStore

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
- Always set project_id if the user mentioned one (e.g. "project ACME", "project-42").
- Never add commentary outside the JSON object.
"""


class Orchestrator:
    def __init__(self, session_id: str = "default"):
        self.client = anthropic.Anthropic()
        self.state = StateStore(session_id=session_id)

    def handle(self, user_input: str) -> dict:
        self.state.add_message("user", user_input)

        routing_response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=self.state.get_messages(),
        )

        raw = routing_response.content[0].text.strip()

        if DEBUG_VERBOSE:
            print(f"\n[Orchestrator] Routing decision:\n{raw}\n")

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
            print(f"\n[Orchestrator] → Dispatching to Planner agent")
            agent_output = run_planner(
                request=routing["request"],
                project_id=project_id or self.state.get_project().project_id,
            )
            self.state.record_milestones(agent_output["milestones"])
            self.state.record_tasks(agent_output["tasks"])
            self.state.record_agent_output("planner", agent_output)
            reply = agent_output["summary"] or "Plan created."
            self.state.add_message("assistant", reply)
            return {"agent_used": "planner", "agent_output": agent_output, "reply": reply}

        # ── Risk Monitor ──────────────────────────────────────────────────────
        elif agent == "risk_monitor":
            print(f"\n[Orchestrator] → Dispatching to Risk Monitor agent")
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

    def get_state_snapshot(self) -> dict:
        return self.state.snapshot()


def _parse_json(text: str) -> dict:
    import json, re
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
