"""Env-backed configuration. Loaded once at import."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

# Groq (free tier — primary brain + STT)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
# Fallback model when the primary hits its daily/per-minute token cap. The 8B-instant
# model has a separate, much larger free-tier quota — so Russell stays alive even
# when the smarter 70B is throttled.
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant").strip()
GROQ_STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3").strip()
# When True, prefer Groq for the LLM and STT; fall back to Emergent (Claude/OpenAI) only on error.
USE_GROQ = bool(GROQ_API_KEY)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
TWILIO_VALIDATE_SIGNATURE = os.environ.get("TWILIO_VALIDATE_SIGNATURE", "true").lower() == "true"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
# Comma-separated chat IDs. Empty = allow all (use only for personal bots).
_raw_allowed = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
TELEGRAM_ALLOWED_CHAT_IDS: set[int] = {
    int(x) for x in _raw_allowed.split(",") if x.strip().lstrip("-").isdigit()
}

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
