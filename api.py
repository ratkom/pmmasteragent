import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from pydantic import BaseModel
from orchestrator import Orchestrator

app = FastAPI(title="PM Master Agent")

sessions: dict[str, Orchestrator] = {}

class MessageRequest(BaseModel):
    message: str
    session_id: str = "default"

@app.post("/chat")
async def chat(req: MessageRequest):
    if req.session_id not in sessions:
        sessions[req.session_id] = Orchestrator()
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