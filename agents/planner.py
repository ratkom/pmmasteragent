"""
Planner Agent
─────────────
Receives a planning request, calls Claude with the planner tool set,
executes any tool calls, and returns the final structured plan.

This is a fully autonomous agentic loop:
  1. Send request to Claude
  2. Claude responds with text and/or tool_use blocks
  3. Execute tool calls, collect results
  4. Feed results back to Claude
  5. Repeat until Claude stops calling tools (end_turn)
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


def run_planner(request: str, project_id: str | None = None) -> dict:
    """
    Run the Planner agent on a planning request.

    Args:
        request:    Natural-language planning request from the orchestrator.
        project_id: Optional existing project ID to plan against.

    Returns:
        {
          "summary": str,          # Agent's final text summary
          "tool_calls": list,      # All tool calls made (name + inputs + result)
          "milestones": list,      # Milestone objects created
          "tasks": list,           # Task objects created
        }
    """
    client = anthropic.Anthropic()

    user_message = request
    if project_id:
        user_message = f"Project ID: {project_id}\n\n{request}"

    messages = [{"role": "user", "content": user_message}]

    # Collected results across the agentic loop
    all_tool_calls = []
    milestones = []
    tasks = []
    final_summary = ""

    if DEBUG_VERBOSE:
        print(f"\n[Planner] Starting with request: {request[:120]}...")

    # ── Agentic loop ──────────────────────────────────────────────────────────
    while True:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8096,
            system=PLANNER_SYSTEM_PROMPT,
            tools=PLANNER_TOOL_SCHEMAS,
            messages=messages,
        )

        if DEBUG_VERBOSE:
            print(f"[Planner] Stop reason: {response.stop_reason}")

        # Collect any text content as a running summary
        for block in response.content:
            if block.type == "text":
                final_summary = block.text

        # If Claude is done, break out of the loop
        if response.stop_reason == "end_turn":
            break

        # If Claude wants to use tools, execute them
        if response.stop_reason == "tool_use":
            # Append Claude's response (including tool_use blocks) to history
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                print(f"\n[Planner → tool] {tool_name}({json.dumps(tool_input, indent=2)})")

                # Execute the stub/real function
                executor = PLANNER_TOOL_EXECUTORS.get(tool_name)
                if executor is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = executor(**tool_input)
                    except Exception as e:
                        result = {"error": str(e)}

                print(f"[tool → Planner] {json.dumps(result, indent=2)}")

                # Track results for the caller
                all_tool_calls.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "result": result,
                })
                if tool_name == "create_milestone":
                    milestones.append(result)
                elif tool_name == "create_task":
                    tasks.append(result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            # Feed results back to Claude for the next iteration
            messages.append({"role": "user", "content": tool_results})

        else:
            # Unexpected stop reason — break to avoid infinite loop
            print(f"[Planner] Unexpected stop reason: {response.stop_reason}")
            break

    return {
        "summary": final_summary,
        "tool_calls": all_tool_calls,
        "milestones": milestones,
        "tasks": tasks,
    }