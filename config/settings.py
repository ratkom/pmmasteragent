import os
from dotenv import load_dotenv
 
load_dotenv()
 
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
DEBUG_VERBOSE = os.getenv("DEBUG_VERBOSE", "false").lower() == "true"
 
if not ANTHROPIC_API_KEY:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY is not set. "
        "Copy .env.example to .env and add your key."
    )