"""
Slack Bot (Step 6)
──────────────────
Listens for @mentions and DMs, forwards them to the orchestrator,
and posts the response back to Slack.

Uses Slack Bolt in Socket Mode for easy local dev,
and HTTP mode for Railway deployment.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from orchestrator import Orchestrator

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")  # for socket mode (local dev)

if not SLACK_BOT_TOKEN:
    raise EnvironmentError("SLACK_BOT_TOKEN is not set in your .env file.")
if not SLACK_SIGNING_SECRET:
    raise EnvironmentError("SLACK_SIGNING_SECRET is not set in your .env file.")

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

# One orchestrator per Slack user session
_sessions: dict[str, Orchestrator] = {}


def get_orchestrator(user_id: str) -> Orchestrator:
    if user_id not in _sessions:
        _sessions[user_id] = Orchestrator(session_id=f"slack_{user_id}")
    return _sessions[user_id]


def format_reply(result: dict) -> str:
    """Format orchestrator output for Slack."""
    reply = result["reply"]
    agent = result.get("agent_used")
    output = result.get("agent_output", {})

    blocks = [f"{reply}"]

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


# ── Event handlers ────────────────────────────────────────────────────────────

@app.event("app_mention")
def handle_mention(event, say, logger):
    """Respond when the bot is @mentioned in a channel."""
    user_id = event["user"]
    # Strip the @mention from the message text
    text = event["text"]
    # Remove the bot mention (format: <@BOTID> message)
    clean_text = " ".join(
        word for word in text.split()
        if not word.startswith("<@")
    ).strip()

    if not clean_text:
        say("Hi! Mention me with a request, e.g. _@PM Master Agent scan for risks_")
        return

    logger.info(f"[Slack] @mention from {user_id}: {clean_text}")

    try:
        say("⏳ On it...")
        orchestrator = get_orchestrator(user_id)
        result = orchestrator.handle(clean_text)
        say(format_reply(result))
    except Exception as e:
        logger.error(f"[Slack] Error: {e}")
        say(f"Sorry, something went wrong: {str(e)}")


@app.event("message")
def handle_dm(event, say, logger):
    logger.info(f"[DEBUG] message event received: {event}")
    
    if event.get("channel_type") != "im":
        logger.info(f"[DEBUG] ignoring - not a DM, channel_type: {event.get('channel_type')}")
        return
    if event.get("bot_id"):
        logger.info(f"[DEBUG] ignoring - bot message")
        return

    user_id = event["user"]
    text = event.get("text", "").strip()
    logger.info(f"[DEBUG] DM from {user_id}: {text}")

    if not text:
        return

    try:
        say("⏳ On it...")
        orchestrator = get_orchestrator(user_id)
        result = orchestrator.handle(text)
        say(format_reply(result))
    except Exception as e:
        logger.error(f"[Slack] Error: {e}")
        say(f"Sorry, something went wrong: {str(e)}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Socket Mode — for local development only
    if not SLACK_APP_TOKEN:
        raise EnvironmentError(
            "SLACK_APP_TOKEN is not set. "
            "Get it from your Slack app settings under 'Socket Mode'."
        )
    print("[Slack] Starting in Socket Mode (local dev)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
