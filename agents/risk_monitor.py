"""
Risk Monitor Agent
──────────────────
Scans Linear for overdue issues, stalled work, and at-risk projects.
Returns structured risk alerts with recommended actions.

Plugs into the orchestrator exactly like the Planner agent.
"""

import json
import anthropic
from config.settings import CLAUDE_MODEL, DEBUG_VERBOSE
from tools.risk_tools import get_overdue_issues, get_stalled_issues, get_projects_at_risk

RISK_MONITOR_SYSTEM_PROMPT = """You are a Risk Monitor agent in a project management system.

Your job:
- Use the tools provided to scan for project risks
- Identify overdue issues, stalled work, and at-risk projects
- Assess severity: critical (blocks delivery), high (significant impact), medium (needs attention)
- Suggest a concrete next action for each risk
- Be direct and specific — no vague advice

Output format after using tools:
1. Overall risk level: CRITICAL / HIGH / MEDIUM / LOW
2. List each risk with: what it is, why it matters, what to do
3. Keep it concise — this is a status report, not an essay

If no risks are found, say so clearly.
"""

RISK_TOOL_SCHEMAS = [
    {
        "name": "get_overdue_issues",
        "description": "Fetch all incomplete Linear issues that are past their due date.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_stalled_issues",
        "description": "Fetch in-progress issues with no activity for N days (default 7).",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_inactive": {
                    "type": "integer",
                    "description": "Number of days without activity to consider an issue stalled",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_projects_at_risk",
        "description": "Fetch projects that are behind schedule or unlikely to hit their target date.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

RISK_TOOL_EXECUTORS = {
    "get_overdue_issues": get_overdue_issues,
    "get_stalled_issues": get_stalled_issues,
    "get_projects_at_risk": get_projects_at_risk,
}


def run_risk_monitor(request: str = "Run a full risk scan") -> dict:
    """
    Run the Risk Monitor agent.

    Args:
        request: Natural-language instruction, e.g. 'What are the current risks?'

    Returns:
        {
          "summary":      str,   # Agent's risk report
          "risk_level":   str,   # CRITICAL / HIGH / MEDIUM / LOW
          "risks":        list,  # Raw tool results
          "tool_calls":   list,  # All tool calls made
        }
    """
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": request}]

    all_tool_calls = []
    all_risks = []
    final_summary = ""

    if DEBUG_VERBOSE:
        print(f"\n[RiskMonitor] Starting scan...")

    # ── Agentic loop ──────────────────────────────────────────────────────────
    while True:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=RISK_MONITOR_SYSTEM_PROMPT,
            tools=RISK_TOOL_SCHEMAS,
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

                print(f"\n[RiskMonitor → tool] {tool_name}()")

                executor = RISK_TOOL_EXECUTORS.get(tool_name)
                if executor is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = executor(**tool_input)
                    except Exception as e:
                        result = {"error": str(e)}

                print(f"[tool → RiskMonitor] found {sum(len(v) for v in result.values() if isinstance(v, list))} items")

                all_tool_calls.append({"tool": tool_name, "result": result})
                all_risks.append(result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            break

    # Extract risk level from summary
    risk_level = "LOW"
    for level in ["CRITICAL", "HIGH", "MEDIUM"]:
        if level in final_summary.upper():
            risk_level = level
            break

    return {
        "summary": final_summary,
        "risk_level": risk_level,
        "risks": all_risks,
        "tool_calls": all_tool_calls,
    }
