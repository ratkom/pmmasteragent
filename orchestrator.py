"""
Orchestrator
────────────
The single entry point for all user requests.

Step 1 responsibilities:
  - Understand what the user is asking for
  - Route to the Planner agent when appropriate
  - Maintain conversation state across turns
  - Return a structured response to the caller (CLI or future API)

Step 2+ will add: Risk monitor, Comms agent, Reporter routing.
"""

import anthropic
from config.settings import CLAUDE_MODEL, DEBUG_VERBOSE
from agents.planner import run_planner
from memory.state_store import StateStore

ORCHESTRATOR_SYSTEM_PROMPT = """You are the orchestrator for an AI-powered project management system.

You analyse each user message and decide which specialist agent to invoke.
You have access to these agents (Step 1 — more will be added):
  - planner: Creates project milestones and tasks from a description

Your response must be a JSON object with this exact shape:
{
  "agent": "planner" | "none",
  "request": "<reformulated request to send to the agent>",
  "project_id": "<project ID if mentioned, else null>",
  "reply_if_no_agent": "<conversational reply if agent is 'none'>"
}

Rules:
- Use "planner" when the user wants to plan a project, create milestones, break down work, or build a roadmap.
- Use "none" for greetings, questions about the system, or anything outside PM scope.
- The "request" field should be a clean, complete instruction for the agent — include all relevant context from the conversation.
- Always set project_id if the user mentioned one (e.g. "project ACME", "project-42").
- Never add commentary outside the JSON object.
"""


class Orchestrator:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.state = StateStore()

    def handle(self, user_input: str) -> dict:
        """
        Process one user turn.

        Returns:
            {
              "agent_used":  str | None,
              "agent_output": dict | None,
              "reply":       str,          # Text to show the user
            }
        """
        self.state.add_message("user", user_input)

        # ── Step 1: Ask Claude to route the request ───────────────────────────
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
        except Exception as e:
            reply = "Sorry, I had trouble understanding that. Could you rephrase?"
            self.state.add_message("assistant", reply)
            return {"agent_used": None, "agent_output": None, "reply": reply}

        agent = routing.get("agent", "none")
        project_id = routing.get("project_id")

        # ── Step 2: Update project context if needed ──────────────────────────
        if project_id and not self.state.get_project().project_id:
            self.state.set_project(project_id)

        # ── Step 3: Dispatch to agent ─────────────────────────────────────────
        if agent == "planner":
            print(f"\n[Orchestrator] → Dispatching to Planner agent")
            agent_output = run_planner(
                request=routing["request"],
                project_id=project_id or self.state.get_project().project_id,
            )
            self.state.record_milestones(agent_output["milestones"])
            self.state.record_tasks(agent_output["tasks"])
            self.state.record_agent_output("planner", agent_output)

            reply = agent_output["summary"] or "Plan created. See tool output above."
            self.state.add_message("assistant", reply)
            return {
                "agent_used": "planner",
                "agent_output": agent_output,
                "reply": reply,
            }

        else:
            # No agent needed — use the conversational reply
            reply = routing.get("reply_if_no_agent", "How can I help with your project?")
            self.state.add_message("assistant", reply)
            return {"agent_used": None, "agent_output": None, "reply": reply}

    def get_state_snapshot(self) -> dict:
        return self.state.snapshot()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Extract and parse JSON from model output, stripping markdown fences."""
    import json, re
    # Strip ```json ... ``` fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)