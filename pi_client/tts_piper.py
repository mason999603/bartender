"""Piper TTS — local, offline voice for Russell.

Synthesises text with `piper-tts` Python package, plays back via `aplay` (which
handles sample-rate conversion the Pi's on-board DAC needs).

This is now fully offline / free — no cloud TTS calls.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import wave
from typing import Optional

logger = logging.getLogger("russell.tts")


class PiperTTS:
    """Lazy-loaded Piper voice. One instance reused across many syntheses."""

    def __init__(self, voice_path: str):
        self.voice_path = voice_path
        self._voice = None

    def _ensure_loaded(self) -> None:
        if self._voice is not None:
            return
        try:
            from piper.voice import PiperVoice
        except ImportError as e:
            raise RuntimeError(
                "piper-tts not installed. `pip install piper-tts` on the Pi."
            ) from e
        logger.info(f"Loading Piper voice: {self.voice_path}")
        self._voice = PiperVoice.load(self.voice_path)

    def synthesize_to_wav(self, text: str, wav_path: str) -> None:
        """Render `text` straight to a wav file on disk."""
        text = (text or "").strip()
        if not text:
            return
        self._ensure_loaded()
        sr = self._voice.config.sample_rate
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            self._voice.synthesize(text, wf)


def speak(tts: PiperTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: synth + play. Uses `aplay` for reliable Pi audio routing."""
    text = (text or "").strip()
    if not text:
        return
    # Strip markdown leftovers Claude/Llama sometimes slip in — Piper reads them literally.
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
            logger.warning(f"Piper synthesis failed: {e}")
            return

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
            logger.warning("Piper produced empty/tiny audio — skipping playback")
            return

        # plughw lets ALSA resample Piper's 22050Hz to whatever the DAC wants.
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
