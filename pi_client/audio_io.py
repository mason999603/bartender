"""Audio recording helpers — VAD-bounded capture from the default input.

We record at the device's native rate (USB mics are usually 48kHz) then output a
16kHz wav, which is what Whisper expects.
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

TARGET_RATE = 16000  # what Whisper STT expects
CHANNELS = 1
DTYPE = "int16"


def _pick_input_settings(input_device: Optional[int]) -> tuple[int, int]:
    """Find a sample-rate + channel-count combo the input device supports.

    Returns (sample_rate, channels). USB mics vary — Yeti likes 48k stereo,
    some cheap mics only do 16k mono. We probe.
    """
    for sr, ch in [
        (TARGET_RATE, 1), (TARGET_RATE, 2),
        (48000, 1), (48000, 2),
        (44100, 1), (44100, 2),
    ]:
        try:
            sd.check_input_settings(
                device=input_device, samplerate=sr, channels=ch, dtype=DTYPE
            )
            return sr, ch
        except Exception:
            continue
    return 48000, 1  # last-ditch guess


def _rms(chunk: np.ndarray) -> float:
    """Root-mean-square amplitude, normalised to 0..1 for int16."""
    if chunk.size == 0:
        return 0.0
    # int16 max is 32768
    samples = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(samples ** 2)))


def _downsample_to_target(audio: np.ndarray, src_rate: int) -> np.ndarray:
    """Resample int16 audio to TARGET_RATE."""
    if src_rate == TARGET_RATE or audio.size == 0:
        return audio
    from scipy.signal import resample_poly
    floats = audio.astype(np.float32) / 32768.0
    gcd = np.gcd(TARGET_RATE, src_rate)
    up = TARGET_RATE // gcd
    down = src_rate // gcd
    resampled = resample_poly(floats, up, down)
    return np.clip(resampled * 32768.0, -32768, 32767).astype(np.int16)


def record_until_silence(
    *,
    silence_threshold: float = 0.015,
    silence_seconds: float = 1.4,
    max_seconds: float = 30.0,
    input_device: Optional[int] = None,
    pre_roll_ms: int = 200,
) -> bytes:
    """Record audio from the mic, stopping after `silence_seconds` of quiet OR `max_seconds` total.

    Returns a fully-formed 16kHz mono WAV file as bytes (ready to POST to /api/voice/transcribe).
    """
    device_rate, device_channels = _pick_input_settings(input_device)
    chunk_ms = 30
    chunk_samples = int(device_rate * chunk_ms / 1000)

    captured: list[np.ndarray] = []
    silent_chunks_needed = int(silence_seconds * 1000 / chunk_ms)
    max_chunks = int(max_seconds * 1000 / chunk_ms)

    silent_count = 0
    started = False
    chunk_count = 0
    start_time = time.time()

    with sd.InputStream(
        samplerate=device_rate,
        channels=device_channels,
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
    # Stereo → mono by averaging channels (the captured frames are interleaved L/R/L/R).
    if device_channels == 2 and audio.size > 0:
        audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)
    audio_16k = _downsample_to_target(audio, device_rate)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(TARGET_RATE)
        wf.writeframes(audio_16k.tobytes())
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
