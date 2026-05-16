"""
Approval Gate (Step 7)
──────────────────────
Intercepts write actions before they execute and requires
explicit confirmation from the user.

Flow:
  1. Agent proposes actions (create_milestone, create_task, etc.)
  2. Gate stores the pending plan in Redis
  3. User sees a summary and types "yes" / "no"
  4. On "yes" → executes the stored plan
  5. On "no"  → discards it
"""

import json
import os
from typing import Callable

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

REDIS_URL = os.getenv("REDIS_URL", "")
PENDING_TTL = 60 * 10  # 10 minutes to confirm

# Tools that require human approval before executing
WRITE_TOOLS = {"create_milestone", "create_task"}

# Tools that run immediately without approval
READ_TOOLS = {"get_project_status", "list_milestones", "get_overdue_issues",
              "get_stalled_issues", "get_projects_at_risk"}

CONFIRMATION_WORDS = {"yes", "y", "confirm", "ok", "go", "do it", "approve"}
REJECTION_WORDS = {"no", "n", "cancel", "stop", "abort", "reject", "nope"}


def _get_redis():
    if REDIS_AVAILABLE and REDIS_URL:
        return redis.from_url(REDIS_URL, decode_responses=True)
    return None


class ApprovalGate:
    """
    Manages pending action approval per session.
    Falls back to in-memory if Redis is unavailable.
    """

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._client = _get_redis()
        self._memory: dict = {}  # fallback

    def _key(self) -> str:
        return f"pm_agent:pending:{self.session_id}"

    def store_pending(self, plan: dict):
        """Store a plan awaiting confirmation."""
        if self._client:
            self._client.setex(self._key(), PENDING_TTL, json.dumps(plan))
        else:
            self._memory[self.session_id] = plan

    def get_pending(self) -> dict | None:
        """Retrieve the pending plan, if any."""
        if self._client:
            val = self._client.get(self._key())
            return json.loads(val) if val else None
        return self._memory.get(self.session_id)

    def clear_pending(self):
        """Discard the pending plan."""
        if self._client:
            self._client.delete(self._key())
        else:
            self._memory.pop(self.session_id, None)

    def has_pending(self) -> bool:
        return self.get_pending() is not None

    def is_confirmation(self, text: str) -> bool:
        return text.lower().strip() in CONFIRMATION_WORDS

    def is_rejection(self, text: str) -> bool:
        return text.lower().strip() in REJECTION_WORDS

    def format_confirmation_prompt(self, plan: dict) -> str:
        """Build a human-readable summary of what's about to happen."""
        lines = ["*Before I proceed, here's what I'm about to do:*\n"]

        milestones = plan.get("proposed_milestones", [])
        tasks = plan.get("proposed_tasks", [])
        request = plan.get("request", "")

        if milestones:
            lines.append(f"*Create {len(milestones)} milestone(s) in Linear:*")
            for m in milestones:
                lines.append(f"  • {m['name']} — due {m['due_date']}")

        if tasks:
            lines.append(f"\n*Create {len(tasks)} task(s) in Linear:*")
            for t in tasks[:5]:  # show first 5
                lines.append(f"  • {t['title']}")
            if len(tasks) > 5:
                lines.append(f"  • ...and {len(tasks) - 5} more")

        lines.append("\nReply *yes* to confirm or *no* to cancel.")
        return "\n".join(lines)


def requires_approval(tool_name: str) -> bool:
    """Return True if this tool needs human approval."""
    return tool_name in WRITE_TOOLS


def extract_proposed_actions(agent_request: str, agent_output: dict) -> dict | None:
    """
    Build a pending plan from what the planner *would* create.
    Returns None if there's nothing to approve (read-only request).
    """
    # If the agent made no write calls, nothing to approve
    tool_calls = agent_output.get("tool_calls", [])
    write_calls = [t for t in tool_calls if t["tool"] in WRITE_TOOLS]

    if not write_calls:
        return None

    # Extract proposed items from tool inputs (not results — not executed yet)
    proposed_milestones = []
    proposed_tasks = []

    for call in write_calls:
        if call["tool"] == "create_milestone":
            proposed_milestones.append(call["input"])
        elif call["tool"] == "create_task":
            proposed_tasks.append(call["input"])

    return {
        "request": agent_request,
        "proposed_milestones": proposed_milestones,
        "proposed_tasks": proposed_tasks,
        "write_calls": write_calls,
    }
