"""Russell's voice on the Pi — cloud TTS via the backend /api/voice/speak endpoint.

We POST the reply text to the backend, it synthesises with OpenAI TTS (voice="onyx"),
returns a WAV blob, the Pi plays it with `aplay`. No local TTS engine, no
sample-rate fights with the on-board DAC.

Module is named `tts_piper.py` for historical reasons — the class is now a
cloud client. The Pi client imports `PiperTTS` and `speak()` so we keep those
names for API compatibility.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

import requests

logger = logging.getLogger("russell.tts")


class PiperTTS:
    """Cloud TTS client. The `voice_path` arg is ignored — kept for API compat."""

    def __init__(self, voice_path: str = "") -> None:
        # voice_path is now unused but kept so the Pi client doesn't need to change.
        del voice_path
        self.backend_url = (os.environ.get("RUSSELL_BACKEND_URL") or "").rstrip("/")
        self.voice = os.environ.get("RUSSELL_TTS_VOICE", "onyx")
        self.model = os.environ.get("RUSSELL_TTS_MODEL", "tts-1")
        if not self.backend_url:
            raise RuntimeError("RUSSELL_BACKEND_URL not set in .env")

    def synthesize_to_wav(self, text: str, wav_path: str) -> None:
        """Fetch a WAV from the backend TTS endpoint and write it to disk."""
        text = (text or "").strip()
        if not text:
            return
        payload = {"text": text, "voice": self.voice, "model": self.model, "format": "wav"}
        r = requests.post(
            f"{self.backend_url}/api/voice/speak",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        with open(wav_path, "wb") as f:
            f.write(r.content)


def speak(tts: PiperTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: synth + play. Uses `aplay` for reliable Pi audio routing."""
    text = (text or "").strip()
    if not text:
        return

    aplay = shutil.which("aplay")
    if not aplay:
        logger.error("aplay not found — install alsa-utils: sudo apt install -y alsa-utils")
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        try:
            tts.synthesize_to_wav(text, wav_path)
        except requests.HTTPError as e:
            logger.warning(f"TTS API error: {e}")
            return
        except requests.RequestException as e:
            logger.warning(f"TTS network error: {e}")
            return

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
            logger.warning("TTS returned empty/tiny audio — skipping playback")
            return

        # plughw lets ALSA resample/reroute the audio to whatever the DAC actually wants.
        target = f"plughw:{output_device},0" if output_device is not None else "default"
        try:
            subprocess.run([aplay, "-q", "-D", target, wav_path], check=True)
        except subprocess.CalledProcessError as e:
            logger.warning(f"aplay failed ({e}) — trying default device")
            try:
                subprocess.run([aplay, "-q", wav_path], check=True)
            except subprocess.CalledProcessError as e2:
                logger.error(f"aplay failed entirely: {e2}")
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
