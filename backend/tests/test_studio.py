"""Russell's Studio API tests — ideas, scripts, save/list/delete, TTS."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://code-snapshot-23.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def test_list_scripts_empty_ok(client):
    r = client.get(f"{API}/studio/scripts", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_generate_ideas(client):
    r = client.post(f"{API}/studio/ideas", json={"topic": "espresso martini", "count": 3}, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "ideas" in data
    ideas = data["ideas"]
    assert isinstance(ideas, list) and len(ideas) >= 1, f"Expected ideas, got {data}"
    for it in ideas:
        assert it.get("title") and it.get("hook")
        plat = it.get("platform", "").lower()
        # lenient — parser may leave blank; platform not always populated
        if plat:
            assert plat in ("tiktok", "youtube-shorts", "youtube-long", "both"), f"bad platform: {plat}"


def test_generate_script(client):
    payload = {
        "title": "Espresso Martini Truth Bomb",
        "hook": "You've been shaking your espresso martini wrong.",
        "angle": "Why coffee temp matters more than technique.",
        "platform": "tiktok",
    }
    r = client.post(f"{API}/studio/script", json=payload, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    md = d.get("script_markdown", "")
    assert md and "## SPOKEN SCRIPT" in md, f"missing SPOKEN SCRIPT section: {md[:200]}"


def test_script_save_list_delete_roundtrip(client):
    # save
    payload = {
        "title": "TEST_studio_roundtrip",
        "hook": "TEST hook",
        "platform": "tiktok",
        "script_markdown": "## SPOKEN SCRIPT\nHello mate.",
    }
    r = client.post(f"{API}/studio/scripts", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert sid

    # list contains
    r = client.get(f"{API}/studio/scripts", timeout=30)
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())

    # delete
    r = client.delete(f"{API}/studio/scripts/{sid}", timeout=30)
    assert r.status_code == 200
    assert r.json().get("deleted") is True

    # list no longer contains
    r = client.get(f"{API}/studio/scripts", timeout=30)
    assert r.status_code == 200
    assert not any(s["id"] == sid for s in r.json())


def test_voice_speak_mp3(client):
    payload = {"text": "Hello mate, welcome to Russell.", "voice": "onyx", "format": "mp3", "model": "tts-1"}
    r = client.post(f"{API}/voice/speak", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "audio/mpeg" in ct, f"bad content-type: {ct}"
    assert len(r.content) > 500
