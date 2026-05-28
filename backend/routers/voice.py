"""Voice (Whisper STT) endpoint — used by web push-to-talk."""
import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from emergentintegrations.llm.openai import OpenAISpeechToText

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
