"""
Planner Agent (Step 7 — with dry-run mode)
───────────────────────────────────────────
dry_run=True  → Claude plans but tools are intercepted, nothing written to Linear
dry_run=False → Tools execute for real (called after user confirms)
"""

import json
import anthropic
from config.settings import CLAUDE_MODEL, DEBUG_VERBOSE
from tools.planner_tools import PLANNER_TOOL_SCHEMAS, PLANNER_TOOL_EXECUTORS

PLANNER_SYSTEM_PROMPT = """You are a senior project planner agent inside a project management system.

Your job:
- Analyse the user's project request
- Break it into milestones and tasks using the tools provided
- Be specific: real milestone names, realistic due dates, concrete task titles
- Always use the tools to actually create the plan — don't just describe it in text
- After creating everything, produce a clean summary of what was created

Rules:
- Create milestones first, then tasks under them
- Tasks should be 1–5 days of effort each (break larger work down)
- If a project_id is mentioned, fetch its current status first before planning
- Be concise in your final summary; the user can see the structured data
"""

DRY_RUN_SYSTEM_PROMPT = """You are a senior project planner agent inside a project management system.

You are in PLANNING MODE — you will call the tools to show what you WOULD create,
but the system will intercept the calls and ask the user to confirm before anything
is actually written to Linear.

Your job:
- Analyse the user's project request
- Call create_milestone and create_task tools as normal
- Produce a clear summary of the plan you're proposing

Be specific: real milestone names, realistic due dates, concrete task titles.
Create milestones first, then tasks under them. Tasks should be 1-5 days effort each.
"""


def run_planner(request: str, project_id: str | None = None, dry_run: bool = False) -> dict:
    """
    Run the Planner agent.

    Args:
        request:    Natural-language planning request.
        project_id: Optional existing project ID.
        dry_run:    If True, intercept write tools and return proposed actions
                    without executing them.

    Returns:
        {
          "summary":    str,
          "tool_calls": list,
          "milestones": list,
          "tasks":      list,
          "dry_run":    bool,
        }
    """
    client = anthropic.Anthropic()

    user_message = request
    if project_id:
        user_message = f"Project ID: {project_id}\n\n{request}"

    messages = [{"role": "user", "content": user_message}]

    all_tool_calls = []
    milestones = []
    tasks = []
    final_summary = ""

    system_prompt = DRY_RUN_SYSTEM_PROMPT if dry_run else PLANNER_SYSTEM_PROMPT

    if DEBUG_VERBOSE:
        print(f"\n[Planner] dry_run={dry_run}, request: {request[:120]}...")

    while True:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8096,
            system=system_prompt,
            tools=PLANNER_TOOL_SCHEMAS,
            messages=messages,
        )

        for block in response.content:
            if block.type == "text":
                final_summary = block.text

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                print(f"\n[Planner → tool] {tool_name}({json.dumps(tool_input)[:80]}...)")

                # In dry_run mode, intercept write tools
                if dry_run and tool_name in {"create_milestone", "create_task"}:
                    # Return a fake success so Claude can complete its plan
                    if tool_name == "create_milestone":
                        result = {
                            "milestone_id": f"PENDING-{abs(hash(tool_input.get('name',''))) % 9000}",
                            "name": tool_input.get("name", ""),
                            "due_date": tool_input.get("due_date", ""),
                            "description": tool_input.get("description", ""),
                            "status": "pending_approval",
                        }
                        milestones.append({**tool_input, "_pending": True})
                    else:
                        result = {
                            "task_id": f"PENDING-{abs(hash(tool_input.get('title',''))) % 9000}",
                            "title": tool_input.get("title", ""),
                            "milestone_id": tool_input.get("milestone_id", ""),
                            "effort_days": tool_input.get("effort_days", 1),
                            "status": "pending_approval",
                        }
                        tasks.append({**tool_input, "_pending": True})
                else:
                    # Execute for real
                    executor = PLANNER_TOOL_EXECUTORS.get(tool_name)
                    if executor is None:
                        result = {"error": f"Unknown tool: {tool_name}"}
                    else:
                        try:
                            result = executor(**tool_input)
                        except Exception as e:
                            result = {"error": str(e)}

                    if tool_name == "create_milestone":
                        milestones.append(result)
                    elif tool_name == "create_task":
                        tasks.append(result)

                all_tool_calls.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "result": result,
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return {
        "summary": final_summary,
        "tool_calls": all_tool_calls,
        "milestones": milestones,
        "tasks": tasks,
        "dry_run": dry_run,
    }
