"""
Planner tools — real Linear integration (Step 3)
Each function calls Linear's GraphQL API via linear_client.py
"""

from tools.linear_client import (
    create_project,
    list_projects,
    create_issue,
    get_project_issues,
)


def create_milestone(name: str, due_date: str, description: str = "") -> dict:
    """Create a Linear project as a milestone."""
    print(f"  [Linear] create_project: '{name}' due {due_date}")
    return create_project(name=name, description=description, target_date=due_date)


def create_task(
    title: str,
    milestone_id: str,
    assignee: str = "unassigned",
    effort_days: int = 1,
    dependencies: list[str] | None = None,
) -> dict:
    """Create a Linear issue under a project."""
    print(f"  [Linear] create_issue: '{title}' → project {milestone_id}")
    result = create_issue(
        title=title,
        project_id=milestone_id,
        assignee=assignee,
        effort_days=effort_days,
    )
    result["dependencies"] = dependencies or []
    return result


def get_project_status(project_id: str) -> dict:
    """Get real project status from Linear."""
    print(f"  [Linear] get_project_issues: {project_id}")
    return get_project_issues(project_id)


def list_milestones(project_id: str = None) -> dict:
    """List all Linear projects as milestones."""
    print(f"  [Linear] list_projects")
    return list_projects()


# ── Tool registry ─────────────────────────────────────────────────────────────

PLANNER_TOOL_SCHEMAS = [
    {
        "name": "create_milestone",
        "description": (
            "Create a new project milestone in Linear with a name, due date, and optional description. "
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
            "Create a task (Linear issue) under an existing milestone (Linear project). "
            "Use this to break milestones into actionable work items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "milestone_id": {"type": "string", "description": "Linear project ID of the parent milestone"},
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
        "description": "Get real-time health, completion percentage, and issue summary for a Linear project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "The Linear project ID"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_milestones",
        "description": "List all Linear projects (milestones), including their status and due dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional — not required for listing"},
            },
            "required": [],
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
