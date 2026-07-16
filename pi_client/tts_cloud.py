"""Cloud TTS — fetches WAV audio from the backend `/api/voice/speak` endpoint.

Backend uses OpenAI TTS via the Emergent universal key. The Pi just plays the
returned WAV bytes through `aplay`. Fully replaces local Piper for TTS while
keeping the same `speak()` signature so `russell_pi_client.py` doesn't care.
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


class CloudTTS:
    """Thin wrapper around POST /api/voice/speak."""

    def __init__(self, base_url: str, voice: str = "onyx", model: str = "tts-1", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.voice = voice
        self.model = model
        self.timeout = timeout

    def synthesize_to_wav(self, text: str, wav_path: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        r = requests.post(
            f"{self.base_url}/api/voice/speak",
            json={"text": text, "voice": self.voice, "model": self.model, "format": "wav"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        with open(wav_path, "wb") as f:
            f.write(r.content)


def speak(tts: CloudTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: cloud-synth + play via `aplay`. Signature matches the old Piper `speak()`."""
    text = (text or "").strip()
    if not text:
        return
    # Strip markdown leftovers the model might slip in — TTS reads them literally.
    text = text.replace("**", "").replace("*", "").replace("`", "")

    aplay = shutil.which("aplay")
    if not aplay:
        logger.error("aplay not found — install with: sudo apt install -y alsa-utils")
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        try:
            tts.synthesize_to_wav(text, wav_path)
        except Exception as e:
            logger.warning(f"Cloud TTS synthesis failed: {e}")
            return

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 200:
            logger.warning("Cloud TTS produced empty/tiny audio — skipping playback")
            return

        # `plughw` lets ALSA handle any sample-rate conversion the DAC needs.
        target = f"plughw:{output_device},0" if output_device is not None else "default"
        try:
            subprocess.run([aplay, "-q", "-D", target, wav_path], check=True)
        except subprocess.CalledProcessError as e:
            logger.warning(f"aplay -D {target} failed ({e}) — trying default device")
            try:
                subprocess.run([aplay, "-q", wav_path], check=True)
            except subprocess.CalledProcessError as e2:
                logger.error(f"aplay failed entirely: {e2}")
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
