"""
Planner tools — stubbed for Step 1.
Each function mirrors what a real integration would do.
Swap the body for a real API call when you're ready for Step 2.
"""

import json
from datetime import date, timedelta


def create_milestone(name: str, due_date: str, description: str = "") -> dict:
    """Create a project milestone. Stub returns a fake milestone ID."""
    print(f"  [STUB] create_milestone: '{name}' due {due_date}")
    return {
        "milestone_id": f"MS-{abs(hash(name)) % 9000 + 1000}",
        "name": name,
        "due_date": due_date,
        "description": description,
        "status": "planned",
    }


def create_task(
    title: str,
    milestone_id: str,
    assignee: str = "unassigned",
    effort_days: int = 1,
    dependencies: list[str] | None = None,
) -> dict:
    """Create a task under a milestone. Stub returns a fake task ID."""
    print(f"  [STUB] create_task: '{title}' → {milestone_id}")
    return {
        "task_id": f"T-{abs(hash(title)) % 9000 + 1000}",
        "title": title,
        "milestone_id": milestone_id,
        "assignee": assignee,
        "effort_days": effort_days,
        "dependencies": dependencies or [],
        "status": "todo",
    }


def get_project_status(project_id: str) -> dict:
    """Fetch overall project status. Stub returns a canned response."""
    print(f"  [STUB] get_project_status: {project_id}")
    today = date.today()
    return {
        "project_id": project_id,
        "name": "Stub Project",
        "health": "on_track",
        "completion_pct": 34,
        "milestones_total": 5,
        "milestones_done": 1,
        "next_milestone": {
            "name": "Alpha release",
            "due_date": str(today + timedelta(days=14)),
        },
        "overdue_tasks": 0,
    }


def list_milestones(project_id: str) -> dict:
    """List all milestones for a project."""
    print(f"  [STUB] list_milestones: {project_id}")
    today = date.today()
    return {
        "project_id": project_id,
        "milestones": [
            {
                "milestone_id": "MS-1001",
                "name": "Discovery & scoping",
                "due_date": str(today - timedelta(days=7)),
                "status": "completed",
            },
            {
                "milestone_id": "MS-1002",
                "name": "Alpha release",
                "due_date": str(today + timedelta(days=14)),
                "status": "in_progress",
            },
            {
                "milestone_id": "MS-1003",
                "name": "Beta release",
                "due_date": str(today + timedelta(days=45)),
                "status": "planned",
            },
        ],
    }


# ── Tool registry ─────────────────────────────────────────────────────────────
# This is what we hand to the Claude API as the `tools` parameter.
# The schema tells Claude when and how to call each function.

PLANNER_TOOL_SCHEMAS = [
    {
        "name": "create_milestone",
        "description": (
            "Create a new project milestone with a name, due date, and optional description. "
            "Use this when the user asks to set up milestones or phases for a project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short milestone name, e.g. 'Alpha release'"},
                "due_date": {"type": "string", "description": "ISO date string, e.g. '2025-08-01'"},
                "description": {"type": "string", "description": "Optional longer description"},
            },
            "required": ["name", "due_date"],
        },
    },
    {
        "name": "create_task",
        "description": (
            "Create a task under an existing milestone. "
            "Use this to break milestones into actionable work items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "milestone_id": {"type": "string", "description": "ID of the parent milestone"},
                "assignee": {"type": "string", "description": "Name or email of the assignee"},
                "effort_days": {"type": "integer", "description": "Estimated effort in working days"},
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task IDs this task depends on",
                },
            },
            "required": ["title", "milestone_id"],
        },
    },
    {
        "name": "get_project_status",
        "description": "Get the current health, completion percentage, and milestone summary for a project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "The project identifier"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_milestones",
        "description": "List all milestones for a project, including their status and due dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "The project identifier"},
            },
            "required": ["project_id"],
        },
    },
]

# Map tool name → Python function for the executor
PLANNER_TOOL_EXECUTORS = {
    "create_milestone": create_milestone,
    "create_task": create_task,
    "get_project_status": get_project_status,
    "list_milestones": list_milestones,
}