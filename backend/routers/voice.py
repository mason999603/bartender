"""Voice (STT + TTS) endpoints — Groq Whisper for STT (free), OpenAI TTS for cloud fallback."""
import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from emergentintegrations.llm.openai import OpenAISpeechToText, OpenAITextToSpeech

from core.config import EMERGENT_LLM_KEY, GROQ_API_KEY, GROQ_STT_MODEL, USE_GROQ

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger("russell.voice")


@router.post("/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    """Transcribe an uploaded audio blob — Groq Whisper if available, else OpenAI Whisper."""
    if not GROQ_API_KEY and not EMERGENT_LLM_KEY:
        raise HTTPException(500, "No STT configured — set GROQ_API_KEY or EMERGENT_LLM_KEY")

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

    prompt = "A bartender talking about cocktails, spirits, ingredients, recipes, and bar service."

    if USE_GROQ:
        # Free path — Groq hosted Whisper Large v3
        from groq import AsyncGroq
        client = AsyncGroq(api_key=GROQ_API_KEY)
        try:
            transcription = await client.audio.transcriptions.create(
                file=(fname, contents),
                model=GROQ_STT_MODEL,
                language="en",
                prompt=prompt,
                response_format="json",
            )
            text = getattr(transcription, "text", None) or ""
            return {"text": text.strip()}
        except Exception as e:
            msg = str(e).lower()
            logger.exception("Groq STT error")
            if "rate" in msg or "limit" in msg or "429" in msg:
                raise HTTPException(429, "Groq STT rate-limited — try again in a sec.")
            # Fall through to OpenAI Whisper if we have a key
            if not EMERGENT_LLM_KEY:
                raise HTTPException(500, f"Transcription failed: {e}")
            logger.warning("Falling back to OpenAI Whisper")

    # Paid fallback — OpenAI Whisper via Emergent key
    buf = io.BytesIO(contents)
    buf.name = fname

    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    try:
        response = await stt.transcribe(
            file=buf,
            model="whisper-1",
            response_format="json",
            language="en",
            prompt=prompt,
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
