import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from orchestrator import Orchestrator

app = FastAPI(title="PM Agent System")

# Session store
sessions: dict[str, Orchestrator] = {}


def get_orchestrator(session_id: str) -> Orchestrator:
    if session_id not in sessions:
        sessions[session_id] = Orchestrator(session_id=session_id)
    return sessions[session_id]


class MessageRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
async def chat(req: MessageRequest):
    orchestrator = get_orchestrator(req.session_id)
    result = orchestrator.handle(req.message)
    return {
        "reply": result["reply"],
        "agent_used": result["agent_used"],
        "plan": result["agent_output"],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/session/{session_id}")
async def session_state(session_id: str):
    return get_orchestrator(session_id).get_state_snapshot()


# ── Slack HTTP endpoint (production) ─────────────────────────────────────────
# Slack sends events to this endpoint when deployed on Railway.

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")

if SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET:
    try:
        from slack_bolt import App
        from slack_bolt.adapter.fastapi import SlackRequestHandler

        slack_app = App(
            token=SLACK_BOT_TOKEN,
            signing_secret=SLACK_SIGNING_SECRET,
        )

        def format_reply(result: dict) -> str:
            reply = result["reply"]
            agent = result.get("agent_used")
            output = result.get("agent_output", {})
            blocks = [reply]

            if agent == "planner" and output:
                milestones = output.get("milestones", [])
                tasks = output.get("tasks", [])
                if milestones:
                    blocks.append("\n*Milestones created:*")
                    for m in milestones:
                        url = m.get("url", "")
                        name = m.get("name", "")
                        due = m.get("due_date", "")
                        link = f"<{url}|{name}>" if url else name
                        blocks.append(f"  • {link} — due {due}")
                if tasks:
                    blocks.append("\n*Tasks created:*")
                    for t in tasks:
                        url = t.get("url", "")
                        identifier = t.get("identifier", "")
                        title = t.get("title", "")
                        link = f"<{url}|{identifier}>" if url else identifier
                        blocks.append(f"  • {link}: {title}")

            elif agent == "risk_monitor" and output:
                risk_level = output.get("risk_level", "LOW")
                emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk_level, "⚪")
                blocks.append(f"\n{emoji} *Overall risk level: {risk_level}*")

            return "\n".join(blocks)

        @slack_app.event("app_mention")
        def handle_mention(event, say):
            user_id = event["user"]
            text = " ".join(
                w for w in event["text"].split() if not w.startswith("<@")
            ).strip()
            if not text:
                say("Hi! Mention me with a request.")
                return
            say("⏳ On it...")
            result = get_orchestrator(f"slack_{user_id}").handle(text)
            say(format_reply(result))

        @slack_app.event("message")
        def handle_dm(event, say):
            if event.get("channel_type") != "im" or event.get("bot_id"):
                return
            user_id = event["user"]
            text = event.get("text", "").strip()
            if not text:
                return
            say("⏳ On it...")
            result = get_orchestrator(f"slack_{user_id}").handle(text)
            say(format_reply(result))

        slack_handler = SlackRequestHandler(slack_app)

        @app.post("/slack/events")
        async def slack_events(req: Request):
            return await slack_handler.handle(req)

        print("[API] Slack endpoint registered at /slack/events")

    except ImportError:
        print("[API] slack-bolt not installed — Slack endpoint skipped")
else:
    print("[API] Slack tokens not set — Slack endpoint skipped")
