"""Env-backed configuration. Loaded once at import."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

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
