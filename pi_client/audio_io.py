"""Audio recording helpers — VAD-bounded capture from the default input.

We record in 16kHz/mono/int16 because that's what both Porcupine and Whisper expect.
"""
from __future__ import annotations

import io
import logging
import time
import wave
from typing import Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger("russell.audio")

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


def _rms(chunk: np.ndarray) -> float:
    """Root-mean-square amplitude, normalised to 0..1 for int16."""
    if chunk.size == 0:
        return 0.0
    # int16 max is 32768
    samples = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(samples ** 2)))


def record_until_silence(
    *,
    silence_threshold: float = 0.015,
    silence_seconds: float = 1.4,
    max_seconds: float = 30.0,
    input_device: Optional[int] = None,
    pre_roll_ms: int = 200,
) -> bytes:
    """Record audio from the mic, stopping after `silence_seconds` of quiet OR `max_seconds` total.

    Returns a fully-formed WAV file as bytes (ready to POST to /api/voice/transcribe).
    """
    chunk_ms = 30
    chunk_samples = int(SAMPLE_RATE * chunk_ms / 1000)

    captured: list[np.ndarray] = []
    silent_chunks_needed = int(silence_seconds * 1000 / chunk_ms)
    max_chunks = int(max_seconds * 1000 / chunk_ms)

    silent_count = 0
    started = False
    chunk_count = 0
    start_time = time.time()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        device=input_device,
        blocksize=chunk_samples,
    ) as stream:
        # Brief pre-roll buffer so the very first syllable isn't clipped.
        pre_roll_chunks = max(0, int(pre_roll_ms / chunk_ms))
        for _ in range(pre_roll_chunks):
            data, _ = stream.read(chunk_samples)
            captured.append(np.array(data).flatten())

        while chunk_count < max_chunks:
            data, _ = stream.read(chunk_samples)
            chunk = np.array(data).flatten()
            captured.append(chunk)
            chunk_count += 1

            level = _rms(chunk)
            if not started:
                if level >= silence_threshold:
                    started = True
                    logger.debug(f"speech start (lvl={level:.4f})")
                continue

            if level < silence_threshold:
                silent_count += 1
                if silent_count >= silent_chunks_needed:
                    logger.debug(f"silence detected after {chunk_count} chunks ({time.time()-start_time:.1f}s)")
                    break
            else:
                silent_count = 0

    audio = np.concatenate(captured) if captured else np.zeros(0, dtype=np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def play_audio_array(samples: np.ndarray, sample_rate: int, output_device: Optional[int] = None) -> None:
    """Blocking playback of a float32 or int16 mono numpy array."""
    if samples.size == 0:
        return
    sd.play(samples, sample_rate, device=output_device, blocking=True)


def play_wav_file(path: str, output_device: Optional[int] = None) -> None:
    """Blocking playback of a wav file."""
    import soundfile as sf  # local import — only needed for ack sounds
    data, sr = sf.read(path, dtype="float32")
    play_audio_array(data, sr, output_device=output_device)
