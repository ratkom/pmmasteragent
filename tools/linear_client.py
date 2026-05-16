"""
Linear API client
─────────────────
Thin wrapper around Linear's GraphQL API.
All agent tools call through here.
"""

import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "daaa2cb7-b483-4c62-a534-b55071473de6")

if not LINEAR_API_KEY:
    raise EnvironmentError("LINEAR_API_KEY is not set in your .env file.")


def _run_query(query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query/mutation against Linear API."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    req = urllib.request.Request(
        LINEAR_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": LINEAR_API_KEY,
        },
    )

    try:
        res = urllib.request.urlopen(req)
        data = json.loads(res.read())
        if "errors" in data:
            raise ValueError(f"Linear API error: {data['errors']}")
        return data["data"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise ValueError(f"Linear HTTP {e.code}: {body}")


# ── Projects ──────────────────────────────────────────────────────────────────

def create_project(name: str, description: str = "", target_date: str = None) -> dict:
    """Create a Linear project (maps to our 'plan')."""
    mutation = """
    mutation CreateProject($input: ProjectCreateInput!) {
        projectCreate(input: $input) {
            success
            project {
                id
                name
                description
                targetDate
                state
                url
            }
        }
    }
    """
    variables = {
        "input": {
            "name": name,
            "description": description,
            "teamIds": [LINEAR_TEAM_ID],
            **({"targetDate": target_date} if target_date else {}),
        }
    }
    data = _run_query(mutation, variables)
    project = data["projectCreate"]["project"]
    return {
        "milestone_id": project["id"],
        "name": project["name"],
        "description": project.get("description", ""),
        "due_date": project.get("targetDate", ""),
        "status": project.get("state", "planned"),
        "url": project.get("url", ""),
    }


def list_projects() -> dict:
    """List all projects in the team."""
    query = """
    query {
        projects {
            nodes {
                id
                name
                targetDate
                state
                completedIssueCountHistory
                issueCountHistory
            }
        }
    }
    """
    data = _run_query(query)
    projects = data["projects"]["nodes"]
    return {
        "milestones": [
            {
                "milestone_id": p["id"],
                "name": p["name"],
                "due_date": p.get("targetDate", ""),
                "status": p.get("state", ""),
            }
            for p in projects
        ]
    }


# ── Issues (tasks) ────────────────────────────────────────────────────────────

def create_issue(
    title: str,
    project_id: str,
    description: str = "",
    assignee: str = "unassigned",
    effort_days: int = 1,
) -> dict:
    """Create a Linear issue under a project."""
    mutation = """
    mutation CreateIssue($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue {
                id
                title
                identifier
                url
                state { name }
                project { id name }
            }
        }
    }
    """
    # Convert effort days to Linear's estimate points (1 point per day)
    variables = {
        "input": {
            "title": title,
            "description": description or f"Estimated effort: {effort_days} day(s)",
            "teamId": LINEAR_TEAM_ID,
            "projectId": project_id,
            "estimate": effort_days,
        }
    }
    data = _run_query(mutation, variables)
    issue = data["issueCreate"]["issue"]
    print(f"  [DEBUG] issue response: {issue}")
    return {
        "task_id": issue["id"],
        "identifier": issue["identifier"],
        "title": issue["title"],
        "milestone_id": project_id,
        "assignee": assignee,
        "effort_days": effort_days,
        "status": issue["state"]["name"],
        "url": issue.get("url", ""),
    }


def get_project_issues(project_id: str) -> dict:
    """Get all issues for a project with completion stats."""
    query = """
    query GetProject($id: String!) {
        project(id: $id) {
            id
            name
            state
            targetDate
            issues {
                nodes {
                    id
                    title
                    identifier
                    state { name type }
                    estimate
                }
            }
        }
    }
    """
    data = _run_query(query, {"id": project_id})
    project = data["project"]
    issues = project["issues"]["nodes"]

    total = len(issues)
    done = sum(1 for i in issues if i["state"]["type"] == "completed")
    overdue = 0  # Would need due dates on issues for this

    return {
        "project_id": project_id,
        "name": project["name"],
        "health": "on_track" if done >= total * 0.5 else "at_risk",
        "completion_pct": int((done / total * 100) if total else 0),
        "milestones_total": total,
        "milestones_done": done,
        "next_milestone": {"name": project["name"], "due_date": project.get("targetDate", "")},
        "overdue_tasks": overdue,
    }
