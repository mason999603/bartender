"""Voice (Whisper STT + OpenAI TTS) endpoints."""
import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from emergentintegrations.llm.openai import OpenAISpeechToText, OpenAITextToSpeech

from core.config import EMERGENT_LLM_KEY

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger("russell.voice")


@router.post("/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    """Transcribe an uploaded audio blob via OpenAI Whisper."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    contents = await audio.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio too large (25 MB max)")
    if len(contents) < 500:
        return {"text": ""}

    fname = audio.filename or "voice.webm"
    if "." not in fname:
        ct = (audio.content_type or "").lower()
        ext = "webm" if "webm" in ct else "mp4" if "mp4" in ct else "wav"
        fname = f"voice.{ext}"

    buf = io.BytesIO(contents)
    buf.name = fname

    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    try:
        response = await stt.transcribe(
            file=buf,
            model="whisper-1",
            response_format="json",
            language="en",
            prompt="A bartender talking about cocktails, spirits, ingredients, recipes, and bar service.",
        )
    except Exception as e:
        msg = str(e).lower()
        logger.exception("STT error")
        if "budget" in msg and "exceeded" in msg:
            raise HTTPException(
                429,
                "Russell's tab is closed for the day, mate — Emergent LLM key budget exceeded.",
            )
        raise HTTPException(500, f"Transcription failed: {e}")

    text = getattr(response, "text", None) or ""
    return {"text": text.strip()}


class SpeakRequest(BaseModel):
    text: str
    voice: str = "onyx"  # deep male voice — closest to Russell's vibe
    model: str = "tts-1"
    format: str = "wav"  # wav is friendliest for `aplay` on the Pi


@router.post("/speak")
async def voice_speak(req: SpeakRequest):
    """Synthesise text → audio bytes using OpenAI TTS. Returns the raw audio."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY not configured")

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "Empty text")
    # Strip markdown leftovers that sometimes slip in from Claude.
    text = text.replace("**", "").replace("*", "").replace("`", "")
    # OpenAI TTS caps at 4096 chars — truncate long replies politely.
    if len(text) > 4000:
        text = text[:3996] + "..."

    tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
    try:
        audio_bytes = await tts.generate_speech(
            text=text,
            model=req.model,
            voice=req.voice,
            response_format=req.format,
        )
    except Exception as e:
        msg = str(e).lower()
        logger.exception("TTS error")
        if "budget" in msg and "exceeded" in msg:
            raise HTTPException(
                429,
                "Russell's tab is closed for the day, mate — Emergent LLM key budget exceeded.",
            )
        raise HTTPException(500, f"TTS failed: {e}")

    media_type = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "audio/L16",
    }.get(req.format, "application/octet-stream")
    return Response(content=audio_bytes, media_type=media_type)
