"""
In-memory state store for Step 1.
Holds the current conversation, active project context, and agent outputs.

Designed so the interface is identical to a Redis-backed version —
swapping the backend in Step 4 requires no changes to the agents or orchestrator.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectContext:
    project_id: str | None = None
    project_name: str | None = None
    milestones: list[dict] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)
    last_agent_output: dict = field(default_factory=dict)


@dataclass
class ConversationState:
    messages: list[dict] = field(default_factory=list)
    project: ProjectContext = field(default_factory=ProjectContext)
    metadata: dict[str, Any] = field(default_factory=dict)


class StateStore:
    """
    Simple in-memory state store.
    One store per conversation session.
    """

    def __init__(self):
        self._state = ConversationState()

    # ── Conversation ──────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        self._state.messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        return list(self._state.messages)

    def clear_messages(self):
        self._state.messages = []

    # ── Project context ───────────────────────────────────────────────────────

    def set_project(self, project_id: str, name: str | None = None):
        self._state.project.project_id = project_id
        if name:
            self._state.project.project_name = name

    def get_project(self) -> ProjectContext:
        return self._state.project

    def record_milestones(self, milestones: list[dict]):
        self._state.project.milestones.extend(milestones)

    def record_tasks(self, tasks: list[dict]):
        self._state.project.tasks.extend(tasks)

    def record_agent_output(self, agent_name: str, output: dict):
        self._state.project.last_agent_output = {"agent": agent_name, **output}

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        p = self._state.project
        return {
            "project_id": p.project_id,
            "project_name": p.project_name,
            "milestones_count": len(p.milestones),
            "tasks_count": len(p.tasks),
            "message_turns": len(self._state.messages),
        }