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
    milestones = agent_output.get("milestones", [])
    tasks = agent_output.get("tasks", [])

    if milestones:
        console.print("\n[bold green]Milestones created[/]")
        t = Table("ID", "Name", "Due date", "Status", show_header=True)
        for m in milestones:
            t.add_row(m.get("milestone_id",""), m.get("name",""), m.get("due_date",""), m.get("status",""))
        console.print(t)

    if tasks:
        console.print("\n[bold green]Tasks created[/]")
        t = Table("Identifier", "Title", "Milestone", "Effort", show_header=True)
        for tk in tasks:
            t.add_row(
                tk.get("identifier", tk.get("task_id", "")),
                tk.get("title", ""),
                tk.get("milestone_id", ""),
                f"{tk.get('effort_days', 1)}d",
            )
        console.print(t)


def print_risks(agent_output: dict):
    risk_level = agent_output.get("risk_level", "LOW")
    color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "cyan", "LOW": "green"}.get(risk_level, "white")
    console.print(f"\n[bold {color}]Overall risk level: {risk_level}[/]")


def main():
    console.print(
        Panel.fit(
            "[bold]PM Agent System[/]\n"
            "[dim]Orchestrator · Planner · Risk Monitor · Linear · Redis[/]\n\n"
            "Try:\n"
            "  [italic]'Plan a mobile app launch for Q3 2025'[/]\n"
            "  [italic]'What are the current project risks?'[/]\n"
            "  [italic]'Scan for overdue and stalled issues'[/]\n\n"
            "Type [bold]exit[/] to quit, [bold]state[/] to inspect memory.",
            title="PM Agents",
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
        elif result["agent_used"] == "risk_monitor" and result["agent_output"]:
            print_risks(result["agent_output"])


if __name__ == "__main__":
    main()
