"""
Linear risk queries — fixed GraphQL types
"""

import json
import urllib.request
import urllib.error
import os
from datetime import date, datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_TEAM_ID = os.getenv("LINEAR_TEAM_ID", "daaa2cb7-b483-4c62-a534-b55071473de6")


def _run_query(query: str, variables: dict = None) -> dict:
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
            raise ValueError(f"Linear API error: {json.dumps(data['errors'])}")
        return data["data"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise ValueError(f"Linear HTTP {e.code}: {body}")


def get_overdue_issues() -> dict:
    """Fetch all incomplete issues past their due date."""
    today = date.today().isoformat()

    query = """
    query OverdueIssues($filter: IssueFilter) {
        issues(filter: $filter) {
            nodes {
                id
                identifier
                title
                dueDate
                state { name type }
                assignee { name }
                project { name }
                priorityLabel
            }
        }
    }
    """
    variables = {
        "filter": {
            "dueDate": {"lt": today},
            "completedAt": {"null": True},
            "canceledAt": {"null": True},
        }
    }

    try:
        data = _run_query(query, variables)
        issues = data["issues"]["nodes"]
        return {
            "overdue_issues": [
                {
                    "id": i["id"],
                    "identifier": i["identifier"],
                    "title": i["title"],
                    "due_date": i.get("dueDate", ""),
                    "state": i["state"]["name"],
                    "assignee": i["assignee"]["name"] if i.get("assignee") else "unassigned",
                    "project": i["project"]["name"] if i.get("project") else "none",
                    "priority": i.get("priorityLabel", "none"),
                }
                for i in issues
            ]
        }
    except Exception as e:
        return {"overdue_issues": [], "error": str(e)}


def get_stalled_issues(days_inactive: int = 7) -> dict:
    """Fetch in-progress issues with no recent activity."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_inactive)).isoformat()

    query = """
    query StalledIssues($filter: IssueFilter) {
        issues(filter: $filter, orderBy: updatedAt) {
            nodes {
                id
                identifier
                title
                updatedAt
                state { name type }
                assignee { name }
                project { name }
                priorityLabel
            }
        }
    }
    """
    variables = {
        "filter": {
            "updatedAt": {"lt": cutoff},
            "completedAt": {"null": True},
            "canceledAt": {"null": True},
            "state": {"type": {"in": ["started", "inProgress"]}},
        }
    }

    try:
        data = _run_query(query, variables)
        issues = data["issues"]["nodes"]
        now = datetime.now(timezone.utc)

        stalled = []
        for i in issues:
            updated_str = i.get("updatedAt", "")
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00")) if updated_str else now
            stalled.append({
                "id": i["id"],
                "identifier": i["identifier"],
                "title": i["title"],
                "last_updated": updated_str,
                "days_inactive": (now - updated).days,
                "state": i["state"]["name"],
                "assignee": i["assignee"]["name"] if i.get("assignee") else "unassigned",
                "project": i["project"]["name"] if i.get("project") else "none",
                "priority": i.get("priorityLabel", "none"),
            })

        return {"stalled_issues": stalled}
    except Exception as e:
        return {"stalled_issues": [], "error": str(e)}


def get_projects_at_risk() -> dict:
    """Fetch projects where completion is behind schedule."""
    query = """
    query ProjectsAtRisk {
        projects {
            nodes {
                id
                name
                targetDate
                state
                progress
            }
        }
    }
    """
    today = datetime.now(timezone.utc).date()

    try:
        data = _run_query(query)
        projects = data["projects"]["nodes"]

        at_risk = []
        for p in projects:
            if p.get("state") in ("completed", "cancelled"):
                continue

            target = p.get("targetDate")
            progress = p.get("progress", 0) or 0
            risk_reasons = []

            if target:
                try:
                    due = date.fromisoformat(target)
                    days_left = (due - today).days
                    if days_left < 0:
                        risk_reasons.append(f"overdue by {abs(days_left)} days")
                    elif days_left < 14 and progress < 0.8:
                        risk_reasons.append(
                            f"due in {days_left} days but only {int(progress * 100)}% complete"
                        )
                except ValueError:
                    pass

            if risk_reasons:
                at_risk.append({
                    "id": p["id"],
                    "name": p["name"],
                    "target_date": target or "none",
                    "progress_pct": int(progress * 100),
                    "risk_reasons": risk_reasons,
                })

        return {"projects_at_risk": at_risk}
    except Exception as e:
        return {"projects_at_risk": [], "error": str(e)}
