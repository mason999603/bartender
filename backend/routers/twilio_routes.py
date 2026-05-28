"""Twilio (SMS + Voice) webhooks."""
import logging

from fastapi import APIRouter, HTTPException, Request, Response

from core.brain import chat_with_russell
from core.config import (
    PUBLIC_BASE_URL,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    TWILIO_VALIDATE_SIGNATURE,
)

router = APIRouter(prefix="/twilio", tags=["twilio"])
logger = logging.getLogger("russell.twilio")


def _xml_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _reconstruct_public_url(request: Request) -> str:
    """Twilio signs the public URL. Behind ingress, request.url is internal — use forwarded headers or PUBLIC_BASE_URL."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/") + request.url.path
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}{request.url.path}"


async def _validate_twilio(request: Request, form: dict) -> None:
    if not TWILIO_VALIDATE_SIGNATURE:
        return
    if not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio auth token not set; skipping signature validation")
        return
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    sig = request.headers.get("x-twilio-signature", "")
    url = _reconstruct_public_url(request)
    if not validator.validate(url, form, sig):
        logger.warning(f"Twilio signature invalid for url={url}")
        raise HTTPException(403, "Invalid Twilio signature")


def _twiml(body_xml: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<Response>{body_xml}</Response>'
    return Response(content=xml, media_type="application/xml")


@router.post("/sms")
async def twilio_sms(request: Request):
    """Twilio webhook: inbound SMS → run through Russell's brain → respond with TwiML <Message>."""
    form = dict(await request.form())
    await _validate_twilio(request, form)

    body = (form.get("Body") or "").strip()
    from_number = form.get("From") or "unknown"

    if not body:
        return _twiml("<Message>Send me something to work with, mate.</Message>")

    logger.info(f"[Twilio SMS] from={from_number} body={body[:80]!r}")
    try:
        reply, _actions = await chat_with_russell(session_id="main", user_text=body, channel="sms")
    except HTTPException as he:
        return _twiml(f"<Message>{_xml_escape(he.detail)}</Message>")
    except Exception:
        logger.exception("SMS chat error")
        return _twiml("<Message>Russell's a bit busy — try again in a sec.</Message>")

    if len(reply) > 1500:
        reply = reply[:1497] + "..."
    return _twiml(f"<Message>{_xml_escape(reply)}</Message>")


@router.post("/voice")
async def twilio_voice(request: Request):
    """Twilio webhook: inbound voice call → greet + open a Gather to listen for the caller."""
    form = dict(await request.form())
    await _validate_twilio(request, form)
    from_number = form.get("From") or "unknown"
    logger.info(f"[Twilio Voice] inbound call from={from_number}")

    greeting = _xml_escape("G'day, Russell here. What're we drinking tonight?")
    body = (
        f'<Say voice="Polly.Russell" language="en-AU">{greeting}</Say>'
        '<Gather input="speech" speechTimeout="auto" language="en-AU" '
        'action="/api/twilio/voice/gather" method="POST">'
        '</Gather>'
        '<Say voice="Polly.Russell" language="en-AU">Didn\'t catch that. Catch you later.</Say>'
        '<Hangup/>'
    )
    return _twiml(body)


@router.post("/voice/gather")
async def twilio_voice_gather(request: Request):
    """Twilio webhook: caller's speech was transcribed (SpeechResult)."""
    form = dict(await request.form())
    await _validate_twilio(request, form)

    spoken = (form.get("SpeechResult") or "").strip()
    confidence = float(form.get("Confidence") or 0)
    logger.info(f"[Twilio Voice] gather speech={spoken!r} confidence={confidence}")

    if not spoken:
        body = (
            '<Say voice="Polly.Russell" language="en-AU">Alright, all yours. Catch you next round.</Say>'
            '<Hangup/>'
        )
        return _twiml(body)

    if any(p in spoken.lower() for p in ["goodbye", "bye", "hang up", "end call", "that's all", "cheers mate"]):
        body = (
            '<Say voice="Polly.Russell" language="en-AU">Cheers mate. See ya.</Say>'
            '<Hangup/>'
        )
        return _twiml(body)

    try:
        reply, _actions = await chat_with_russell(session_id="main", user_text=spoken, channel="voice")
    except HTTPException as he:
        body = (
            f'<Say voice="Polly.Russell" language="en-AU">{_xml_escape(he.detail)}</Say>'
            '<Hangup/>'
        )
        return _twiml(body)
    except Exception:
        logger.exception("Voice chat error")
        body = (
            '<Say voice="Polly.Russell" language="en-AU">Bit of static on my end. Try again in a sec.</Say>'
            '<Hangup/>'
        )
        return _twiml(body)

    safe_reply = _xml_escape(reply)
    body = (
        f'<Say voice="Polly.Russell" language="en-AU">{safe_reply}</Say>'
        '<Gather input="speech" speechTimeout="auto" language="en-AU" '
        'action="/api/twilio/voice/gather" method="POST">'
        '</Gather>'
        '<Say voice="Polly.Russell" language="en-AU">Still there? Catch you later.</Say>'
        '<Hangup/>'
    )
    return _twiml(body)


@router.get("/status")
async def twilio_status():
    """Quick check of Twilio configuration (no secrets exposed)."""
    return {
        "configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER),
        "has_account_sid": bool(TWILIO_ACCOUNT_SID),
        "has_auth_token": bool(TWILIO_AUTH_TOKEN),
        "phone_number_configured": bool(TWILIO_PHONE_NUMBER),
        "signature_validation": TWILIO_VALIDATE_SIGNATURE,
        "public_base_url": PUBLIC_BASE_URL or "(auto-detect from request headers)",
    }
