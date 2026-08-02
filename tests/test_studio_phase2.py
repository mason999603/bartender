"""Russell's Studio Phase 2 — Sora hero clips, GPT-Image cards, voiceover, ffmpeg assembly."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# Shared state across tests
_state = {}


# ─── Voiceover (sync) ──────────────────────────────────────────────────────
def test_voiceover_creates_mp3(client):
    payload = {
        "text": "Alright mate, listen. Nine out of ten bartenders overpour their vermouth. Here is how to fix it.",
        "voice": "onyx",
    }
    r = client.post(f"{API}/studio/jobs/voiceover", json=payload, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done"
    assert d["filename"].endswith(".mp3")
    assert d["url"].startswith("/api/studio/media/")
    assert d["bytes"] > 1000
    _state["voice_filename"] = d["filename"]
    _state["voice_job_id"] = d["id"]


# ─── Image card (sync) ─────────────────────────────────────────────────────
def test_image_card_low(client):
    r = client.post(
        f"{API}/studio/jobs/image-card",
        json={"prompt": "moody dark speakeasy bar amber lighting", "quality": "low"},
        timeout=180,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done"
    assert d["filename"].endswith(".png")
    assert d["bytes"] > 10000
    _state["image_filename"] = d["filename"]


# ─── Validation on hero-clip ───────────────────────────────────────────────
def test_hero_clip_invalid_duration(client):
    r = client.post(
        f"{API}/studio/jobs/hero-clip",
        json={"prompt": "test", "aspect": "portrait", "duration": 5, "model": "sora-2"},
        timeout=30,
    )
    assert r.status_code == 400


def test_hero_clip_invalid_model(client):
    r = client.post(
        f"{API}/studio/jobs/hero-clip",
        json={"prompt": "test", "aspect": "portrait", "duration": 4, "model": "sora-3"},
        timeout=30,
    )
    assert r.status_code == 400


def test_hero_clip_square_not_allowed_on_sora2(client):
    r = client.post(
        f"{API}/studio/jobs/hero-clip",
        json={"prompt": "test", "aspect": "square", "duration": 4, "model": "sora-2"},
        timeout=30,
    )
    assert r.status_code == 400


# ─── Hero clip (async — Sora 2) ────────────────────────────────────────────
def _poll(client, job_id, timeout=180, interval=10):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        r = client.get(f"{API}/studio/jobs/{job_id}", timeout=30)
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(interval)
    return last


def test_hero_clip_render(client):
    payload = {
        "prompt": "cinematic slow-mo whisky pour",
        "aspect": "portrait",
        "duration": 4,
        "model": "sora-2",
    }
    r = client.post(f"{API}/studio/jobs/hero-clip", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "queued"
    job_id = d["id"]

    result = _poll(client, job_id, timeout=200, interval=10)
    assert result is not None
    if result["status"] == "failed" and "safety" in (result.get("error") or "").lower():
        # Retry with a benign prompt
        r2 = client.post(
            f"{API}/studio/jobs/hero-clip",
            json={
                "prompt": "a still life of a rocks glass with amber liquid, cinematic",
                "aspect": "portrait",
                "duration": 4,
                "model": "sora-2",
            },
            timeout=30,
        )
        assert r2.status_code == 200
        job_id = r2.json()["id"]
        result = _poll(client, job_id, timeout=200, interval=10)

    assert result["status"] == "done", f"Sora job did not complete: {result}"
    out = result["output"]
    assert out["filename"].endswith(".mp4")
    assert out["bytes"] > 100000
    _state["hero_filename"] = out["filename"]
    _state["hero_job_id"] = job_id


# ─── Assemble ──────────────────────────────────────────────────────────────
def test_assemble_and_download(client):
    hero = _state.get("hero_filename")
    voice = _state.get("voice_filename")
    if not (hero and voice):
        pytest.skip("Prereq hero/voice not available")

    r = client.post(
        f"{API}/studio/jobs/assemble",
        json={
            "hero_filename": hero,
            "voice_filename": voice,
            "caption": "Nine of ten bartenders overpour.",
        },
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "queued"
    job_id = d["id"]

    result = _poll(client, job_id, timeout=180, interval=5)
    assert result["status"] == "done", f"Assemble failed: {result}"
    fname = result["output"]["filename"]
    assert fname.endswith(".mp4")
    _state["final_filename"] = fname

    # Download
    r = client.get(f"{API}/studio/media/{fname}", timeout=60)
    assert r.status_code == 200
    assert "video/mp4" in r.headers.get("content-type", "")
    assert len(r.content) > 10000


# ─── Jobs list ─────────────────────────────────────────────────────────────
def test_jobs_list_includes(client):
    r = client.get(f"{API}/studio/jobs", timeout=30)
    assert r.status_code == 200
    jobs = r.json()
    assert isinstance(jobs, list) and len(jobs) > 0
    ids = {j["id"] for j in jobs}
    # Should include most of our created jobs
    for key in ("voice_job_id", "hero_job_id"):
        if key in _state:
            assert _state[key] in ids, f"Missing {key} in jobs list"
