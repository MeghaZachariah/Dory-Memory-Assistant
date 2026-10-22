"""All settings for Dory's AI layer live here, so nothing is hard-coded elsewhere.

Every value can be overridden with an environment variable (or a .env file
loaded by the app). Model IDs MUST be checked against your account:

    python -m backend.ai.scripts.list_models

and then set DORY_MODEL_NANO / DORY_MODEL_SUPER / DORY_MODEL_ULTRA.
"""
import os
from pathlib import Path

# --- Nebius Token Factory -------------------------------------------------
# OpenAI-compatible endpoint. The API key is read from NEBIUS_API_KEY.
BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
API_KEY_ENV = "NEBIUS_API_KEY"

# Default IDs are best guesses at the Nemotron 3 names. Verify with list_models.
MODELS = {
    "nano": os.getenv("DORY_MODEL_NANO", "nvidia/Nemotron-3-Nano-30B-A3B"),
    "super": os.getenv("DORY_MODEL_SUPER", "nvidia/Nemotron-3-Super-120B-A12B"),
    "ultra": os.getenv("DORY_MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550B-A55B"),
}

# Which tier does which job. Change here after measuring speed.
TIER_FOR = {
    "answer": os.getenv("DORY_TIER_ANSWER", "nano"),      # live conversation turns
    "classify": os.getenv("DORY_TIER_CLASSIFY", "nano"),  # medication / health triage
    "extract": os.getenv("DORY_TIER_EXTRACT", "super"),   # facts from evening chat
    "check": os.getenv("DORY_TIER_CHECK", "super"),       # lie-catcher
    "briefing": os.getenv("DORY_TIER_BRIEFING", "super"), # morning briefing
    "summary": os.getenv("DORY_TIER_SUMMARY", "ultra"),   # daily family summary
}

# Nemotron 3 models can "think" before answering. Thinking makes replies slow,
# so it is switched off for every call unless you set this to "0".
DISABLE_THINKING = os.getenv("DORY_DISABLE_THINKING", "1") == "1"

REQUEST_TIMEOUT_S = float(os.getenv("DORY_TIMEOUT_S", "30"))
MAX_RETRIES = int(os.getenv("DORY_MAX_RETRIES", "2"))
LATENCY_TARGET_MS = int(os.getenv("DORY_LATENCY_TARGET_MS", "3000"))

# Where every model call is logged (one JSON object per line) for the scorecard.
LOG_PATH = Path(os.getenv("DORY_LOG_PATH", Path(__file__).parent / "logs" / "model_calls.jsonl"))

# How many stored facts to put in the answering prompt (newest first).
MAX_FACTS_IN_PROMPT = int(os.getenv("DORY_MAX_FACTS", "200"))

# Lie-catcher settings. The code checks always run. The second model call can be
# turned off if replies are too slow; if it errors, the answer is blocked (fail closed).
MODEL_CHECK_ENABLED = os.getenv("DORY_MODEL_CHECK", "1") == "1"
CHECKER_FAIL_CLOSED = os.getenv("DORY_CHECKER_FAIL_CLOSED", "1") == "1"

# Fixed replies. These are never written by the model.
SAFE_UNKNOWN_REPLY = "I'm not sure. Shall I ask your family?"
SAFE_UNKNOWN_ASKED_REPLY = "I'm not sure about that. I've asked your family, and I'll tell you when they reply."
SAFE_REFUSED_REPLY = "I can't help with that one, but your family can. I'll let them know."
STATEMENT_REPLY = "Thank you for telling me."
ERROR_REPLY ="Sorry, I didn't catch that. Could you say it again?"
