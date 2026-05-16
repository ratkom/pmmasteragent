import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel
from orchestrator import Orchestrator

app = FastAPI(title="PM Agent System")

# Session store — each session_id gets its own orchestrator
# State is persisted in Redis so restarts don't lose context
sessions: dict[str, Orchestrator] = {}


class MessageRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/chat")
async def chat(req: MessageRequest):
    if req.session_id not in sessions:
        sessions[req.session_id] = Orchestrator(session_id=req.session_id)
    orchestrator = sessions[req.session_id]
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
    """Inspect the current state of a session — useful for debugging."""
    if session_id not in sessions:
        sessions[session_id] = Orchestrator(session_id=session_id)
    return sessions[session_id].get_state_snapshot()
