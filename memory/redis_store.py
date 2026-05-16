"""
Redis-backed state store (Step 4)
──────────────────────────────────
Drop-in replacement for memory/state_store.py.
Same interface — no changes needed in orchestrator.py.

Falls back to in-memory if Redis is unavailable (safe for local dev
without Redis running).
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

REDIS_URL = os.getenv("REDIS_URL", "")
SESSION_TTL = 60 * 60 * 24  # 24 hours


def _get_client():
    if REDIS_AVAILABLE and REDIS_URL:
        return redis.from_url(REDIS_URL, decode_responses=True)
    return None


# ── Fallback in-memory store (used locally without Redis) ─────────────────────

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


# ── Redis store ───────────────────────────────────────────────────────────────

class StateStore:
    """
    Redis-backed state store with in-memory fallback.
    One instance per session_id.
    """

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._client = _get_client()
        self._fallback = ConversationState()  # used when Redis unavailable

        if self._client:
            print(f"[StateStore] Using Redis for session: {session_id}")
        else:
            print(f"[StateStore] Redis unavailable — using in-memory for session: {session_id}")

    # ── Internal Redis helpers ────────────────────────────────────────────────

    def _key(self, suffix: str) -> str:
        return f"pm_agent:{self.session_id}:{suffix}"

    def _redis_get(self, suffix: str, default=None):
        if not self._client:
            return default
        try:
            val = self._client.get(self._key(suffix))
            return json.loads(val) if val else default
        except Exception:
            return default

    def _redis_set(self, suffix: str, value):
        if not self._client:
            return
        try:
            self._client.setex(
                self._key(suffix),
                SESSION_TTL,
                json.dumps(value),
            )
        except Exception:
            pass

    # ── Conversation ──────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str):
        if self._client:
            messages = self._redis_get("messages", [])
            messages.append({"role": role, "content": content})
            self._redis_set("messages", messages)
        else:
            self._fallback.messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        if self._client:
            return self._redis_get("messages", [])
        return list(self._fallback.messages)

    def clear_messages(self):
        if self._client:
            self._redis_set("messages", [])
        else:
            self._fallback.messages = []

    # ── Project context ───────────────────────────────────────────────────────

    def set_project(self, project_id: str, name: str | None = None):
        if self._client:
            project = self._redis_get("project", {})
            project["project_id"] = project_id
            if name:
                project["project_name"] = name
            self._redis_set("project", project)
        else:
            self._fallback.project.project_id = project_id
            if name:
                self._fallback.project.project_name = name

    def get_project(self) -> ProjectContext:
        if self._client:
            project = self._redis_get("project", {})
            ctx = ProjectContext()
            ctx.project_id = project.get("project_id")
            ctx.project_name = project.get("project_name")
            ctx.milestones = project.get("milestones", [])
            ctx.tasks = project.get("tasks", [])
            return ctx
        return self._fallback.project

    def record_milestones(self, milestones: list[dict]):
        if self._client:
            project = self._redis_get("project", {})
            existing = project.get("milestones", [])
            existing.extend(milestones)
            project["milestones"] = existing
            self._redis_set("project", project)
        else:
            self._fallback.project.milestones.extend(milestones)

    def record_tasks(self, tasks: list[dict]):
        if self._client:
            project = self._redis_get("project", {})
            existing = project.get("tasks", [])
            existing.extend(tasks)
            project["tasks"] = existing
            self._redis_set("project", project)
        else:
            self._fallback.project.tasks.extend(tasks)

    def record_agent_output(self, agent_name: str, output: dict):
        if self._client:
            self._redis_set("last_output", {"agent": agent_name, **output})
        else:
            self._fallback.project.last_agent_output = {"agent": agent_name, **output}

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        p = self.get_project()
        return {
            "session_id": self.session_id,
            "backend": "redis" if self._client else "in-memory",
            "project_id": p.project_id,
            "project_name": p.project_name,
            "milestones_count": len(p.milestones),
            "tasks_count": len(p.tasks),
            "message_turns": len(self.get_messages()),
        }
