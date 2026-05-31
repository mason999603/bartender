"""Env-backed configuration. Loaded once at import."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"

# Groq (free tier — secondary/fallback brain + STT)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
# Fallback model when the primary hits its daily/per-minute token cap. The 8B-instant
# model has a separate, much larger free-tier quota — so Russell stays alive even
# when the smarter 70B is throttled.
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant").strip()
GROQ_STT_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3").strip()
# When True, prefer Groq for the LLM and STT; fall back to Emergent (Claude/OpenAI) only on error.
USE_GROQ = bool(GROQ_API_KEY)

# OpenRouter (PRIMARY free-model rotation chain — biggest free quota by far).
# Rotation order: best-quality first, fall through to next on rate-limit.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()
# These IDs are :free variants — OpenRouter rate-limits them at 20 RPM, 50/day per key
# (1000/day if you've ever bought ≥$10 credit). Each model has its own daily bucket,
# so rotating across 5+ effectively multiplies your headroom.
OPENROUTER_MODELS = [
    m.strip() for m in os.environ.get(
        "OPENROUTER_MODELS",
        # Verified live on OpenRouter free tier (Feb 2026). Ordered best-to-worst
        # chat quality; mixed providers so they don't all share the same rate-limit bucket.
        "deepseek/deepseek-v4-flash:free,"
        "nvidia/nemotron-3-super-120b-a12b:free,"
        "moonshotai/kimi-k2.6:free,"
        "meta-llama/llama-3.3-70b-instruct:free,"
        "qwen/qwen3-next-80b-a3b-instruct:free,"
        "google/gemma-4-31b-it:free,"
        "openai/gpt-oss-120b:free,"
        "z-ai/glm-4.5-air:free"
    ).split(",") if m.strip()
]
# When True, prefer OpenRouter ahead of Groq.
USE_OPENROUTER = bool(OPENROUTER_API_KEY)
# OpenRouter recommends sending HTTP-Referer and X-Title for attribution on free models.
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "https://russell.local").strip()
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "Russell AI Bartender").strip()

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
