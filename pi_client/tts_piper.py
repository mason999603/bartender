"""Piper TTS — local, offline Aussie voice for Russell.

Wraps the `piper-tts` Python package. Synthesises text → numpy audio → playback.
Voice model lives outside the repo (download from
https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_AU/southern_english_male/medium).
"""
from __future__ import annotations

import logging
import wave
from io import BytesIO
from typing import Optional

import numpy as np

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

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """Return (samples_int16, sample_rate). Caller plays it back."""
        self._ensure_loaded()
        sr = self._voice.config.sample_rate
        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sr)
            self._voice.synthesize(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            n = wf.getnframes()
            raw = wf.readframes(n)
        samples = np.frombuffer(raw, dtype=np.int16)
        return samples, sr


def speak(tts: PiperTTS, text: str, output_device: Optional[int] = None) -> None:
    """Top-level: synth + play. Skips empty text gracefully."""
    text = (text or "").strip()
    if not text:
        return
    # Piper handles punctuation well; just strip markdown asterisks if Claude slipped any in.
    text = text.replace("**", "").replace("*", "").replace("`", "")
    samples, sr = tts.synthesize(text)
    from audio_io import play_audio_array
    play_audio_array(samples, sr, output_device=output_device)
