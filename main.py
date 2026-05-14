"""
PM Agent System — interactive CLI
Run: python main.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from orchestrator import Orchestrator

console = Console()


def print_plan(agent_output: dict):
    """Pretty-print the plan created by the Planner agent."""
    milestones = agent_output.get("milestones", [])
    tasks = agent_output.get("tasks", [])

    if milestones:
        console.print("\n[bold green]Milestones created[/]")
        t = Table("ID", "Name", "Due date", "Status", show_header=True)
        for m in milestones:
            t.add_row(m["milestone_id"], m["name"], m["due_date"], m["status"])
        console.print(t)

    if tasks:
        console.print("\n[bold green]Tasks created[/]")
        t = Table("ID", "Title", "Milestone", "Effort", "Assignee", show_header=True)
        for tk in tasks:
            t.add_row(
                tk["task_id"],
                tk["title"],
                tk["milestone_id"],
                f"{tk['effort_days']}d",
                tk["assignee"],
            )
        console.print(t)


def main():
    console.print(
        Panel.fit(
            "[bold]PM Agent System[/] — Step 1\n"
            "[dim]Orchestrator + Planner agent (stubbed tools)[/]\n\n"
            "Try: [italic]'Plan a mobile app launch for Q3'[/]\n"
            "Type [bold]exit[/] to quit, [bold]state[/] to inspect memory.",
            title="🤖 PM Agents",
        )
    )

    orchestrator = Orchestrator()

    while True:
        try:
            user_input = console.input("\n[bold cyan]You:[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            console.print("[dim]Goodbye.[/]")
            break

        if user_input.lower() == "state":
            rprint(orchestrator.get_state_snapshot())
            continue

        console.print("\n[dim]Processing...[/]")
        result = orchestrator.handle(user_input)

        console.print(f"\n[bold magenta]PM Agent:[/] {result['reply']}")

        if result["agent_used"] == "planner" and result["agent_output"]:
            print_plan(result["agent_output"])


if __name__ == "__main__":
    main()