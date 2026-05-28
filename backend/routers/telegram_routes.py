"""Telegram Bot integration — webhook receiver + admin endpoints.

Architecture:
    Telegram → POST /api/telegram/webhook → chat_with_russell → sendMessage back
    One brain across channels (session_id='main' matches web/SMS/voice).

Security:
    Telegram supports a `secret_token` header set when registering the webhook.
    We verify it on every inbound request via the X-Telegram-Bot-Api-Secret-Token header.

Setup flow:
    1) User creates a bot via @BotFather → gets bot token.
    2) User puts token in TELEGRAM_BOT_TOKEN env var.
    3) User hits POST /api/telegram/setup → we register the webhook with Telegram,
       generating a webhook secret if none is set, and persisting it to memory for this process.
    4) Done. Inbound messages flow.
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from core import config
from core.brain import chat_with_russell

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger("russell.telegram")

TELEGRAM_API = "https://api.telegram.org"


def _bot_token() -> str:
    if not config.TELEGRAM_BOT_TOKEN:
        raise HTTPException(503, "Telegram bot not configured — set TELEGRAM_BOT_TOKEN in backend .env")
    return config.TELEGRAM_BOT_TOKEN


async def _tg_call(method: str, payload: dict | None = None) -> dict:
    """POST to Telegram Bot API and return the JSON `result`. Raises on `ok=false`."""
    url = f"{TELEGRAM_API}/bot{_bot_token()}/{method}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(url, json=payload or {})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not data.get("ok"):
        raise HTTPException(r.status_code if r.status_code >= 400 else 502,
                            f"Telegram API error: {data.get('description') or r.text[:300]}")
    return data["result"]


async def _send_message(chat_id: int, text: str, *, reply_to: Optional[int] = None) -> None:
    """Send a plain-text message. We deliberately skip parse_mode to avoid markdown escaping hell."""
    if not text:
        return
    # Telegram caps message bodies at 4096 chars.
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
    for i, chunk in enumerate(chunks):
        payload: dict = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if reply_to and i == 0:
            payload["reply_to_message_id"] = reply_to
        try:
            await _tg_call("sendMessage", payload)
        except HTTPException as he:
            logger.warning(f"sendMessage failed for chat={chat_id}: {he.detail}")
            raise


async def _send_typing(chat_id: int) -> None:
    try:
        await _tg_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:  # best-effort, never block on this
        pass


# ============================================================
# Routes
# ============================================================

@router.get("/status")
async def telegram_status():
    """Configuration + live webhook info (no secrets exposed)."""
    out: dict = {
        "configured": bool(config.TELEGRAM_BOT_TOKEN),
        "has_token": bool(config.TELEGRAM_BOT_TOKEN),
        "webhook_secret_set": bool(config.TELEGRAM_WEBHOOK_SECRET),
        "allowed_chat_ids": sorted(config.TELEGRAM_ALLOWED_CHAT_IDS) or "(open — any chat can talk to Russell)",
        "bot": None,
        "webhook": None,
    }
    if not config.TELEGRAM_BOT_TOKEN:
        return out

    # Best-effort live lookups
    try:
        me = await _tg_call("getMe")
        out["bot"] = {"id": me.get("id"), "username": me.get("username"), "name": me.get("first_name")}
    except HTTPException as he:
        out["bot"] = {"error": he.detail}

    try:
        wh = await _tg_call("getWebhookInfo")
        out["webhook"] = {
            "url": wh.get("url"),
            "pending_update_count": wh.get("pending_update_count"),
            "last_error_message": wh.get("last_error_message"),
            "last_error_date": wh.get("last_error_date"),
        }
    except HTTPException as he:
        out["webhook"] = {"error": he.detail}

    return out


class SetupRequest(BaseModel):
    public_base_url: Optional[str] = None  # e.g. https://yourapp.preview.emergentagent.com


@router.post("/setup")
async def telegram_setup(req: SetupRequest):
    """Register this backend as the bot's webhook.

    If TELEGRAM_WEBHOOK_SECRET isn't set, a fresh one is generated and stored in-process
    (and we tell the user to copy it into .env to make it persistent across restarts).
    """
    # Fail fast if the bot token isn't configured — don't mutate any state.
    _bot_token()

    base = (req.public_base_url or config.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        raise HTTPException(400, "Provide `public_base_url` in the request body or set PUBLIC_BASE_URL in .env")

    secret = config.TELEGRAM_WEBHOOK_SECRET
    generated = False
    if not secret:
        secret = secrets.token_urlsafe(24)
        generated = True

    webhook_url = f"{base}/api/telegram/webhook"
    result = await _tg_call("setWebhook", {
        "url": webhook_url,
        "secret_token": secret,
        "drop_pending_updates": True,
        "allowed_updates": ["message"],
    })

    # Only persist the generated secret in-process AFTER Telegram accepts the webhook.
    if generated:
        config.TELEGRAM_WEBHOOK_SECRET = secret

    return {
        "ok": True,
        "webhook_url": webhook_url,
        "telegram_result": result,
        "webhook_secret": secret if generated else None,
        "warning": (
            "A fresh webhook secret was generated. Add this to /app/backend/.env as "
            "TELEGRAM_WEBHOOK_SECRET so it survives backend restarts."
            if generated else None
        ),
    }


@router.post("/teardown")
async def telegram_teardown():
    """Remove the webhook from Telegram (useful when migrating environments)."""
    result = await _tg_call("deleteWebhook", {"drop_pending_updates": False})
    return {"ok": True, "telegram_result": result}


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """Inbound update from Telegram. Verifies secret, routes text messages through Russell's brain."""
    # Refuse to process anything until the bot is fully wired up — otherwise we'd be
    # accepting unauthenticated POSTs from the public internet (LLM budget abuse risk).
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "telegram bot not configured")
    if x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
        logger.warning("Rejected Telegram webhook with bad/missing secret token")
        raise HTTPException(403, "bad secret token")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}  # ignore non-message updates (we asked for only `message` anyway)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return {"ok": True}

    # Optional allowlist gate
    if config.TELEGRAM_ALLOWED_CHAT_IDS and chat_id not in config.TELEGRAM_ALLOWED_CHAT_IDS:
        logger.info(f"[telegram] denying chat_id={chat_id} (not in allowlist)")
        try:
            await _send_message(chat_id, "Sorry mate — this bot's set to private. Russell can't chat with strangers.")
        except Exception:
            pass
        return {"ok": True}

    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")

    # Special commands
    if text in ("/start", "/help"):
        await _send_message(chat_id, (
            "G'day, I'm Russell — your bartender mate on call. "
            "Talk to me like a normal human. Ask for a spec, tell me what you're sipping, "
            "or just say what's on your mind."
        ), reply_to=msg_id)
        return {"ok": True}
    if text == "/whoami":
        await _send_message(chat_id, f"You're chat_id {chat_id}. Pop that in TELEGRAM_ALLOWED_CHAT_IDS to lock the bot to just you.")
        return {"ok": True}

    if not text:
        # Non-text message — voice/photo/sticker. Politely decline for now.
        await _send_message(chat_id, "Text only for now, mate — voice notes and photos are on the to-do list.")
        return {"ok": True}

    # Show typing while we think
    await _send_typing(chat_id)

    try:
        reply, actions = await chat_with_russell(session_id="main", user_text=text, channel="telegram")
    except HTTPException as he:
        await _send_message(chat_id, str(he.detail))
        return {"ok": True}
    except Exception:
        logger.exception("[telegram] chat error")
        await _send_message(chat_id, "Russell's a bit foggy — try again in a sec.")
        return {"ok": True}

    # If Russell saved anything, append a small confirmation marker so the user sees it on Telegram.
    from core.actions import summarize_for_channel
    suffix = summarize_for_channel(actions)
    if suffix:
        reply = (reply + "\n\n" + suffix.strip()).strip()

    await _send_message(chat_id, reply, reply_to=msg_id)
    return {"ok": True}
