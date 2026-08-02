"""Backend tests for YouTube publish flow — no Google creds configured."""
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback for backend-only runs; read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"

MEDIA_DIR = "/app/backend/generated/studio"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


# 1) status without creds ----------------------------------------------------
def test_status_disconnected(s, mongo):
    # Ensure no token
    mongo.youtube_auth.delete_many({})
    r = s.get(f"{API}/youtube/status")
    assert r.status_code == 200
    data = r.json()
    assert data.get("connected") is False


# 2) login without creds -----------------------------------------------------
def test_login_returns_503(s):
    r = s.get(f"{API}/youtube/login")
    assert r.status_code == 503
    detail = r.json().get("detail", "")
    assert "YouTube not configured" in detail
    assert "YOUTUBE_CLIENT_ID" in detail
    assert "YOUTUBE_CLIENT_SECRET" in detail
    assert "YOUTUBE_REDIRECT_URI" in detail


# 3) publish disconnected → 401 ---------------------------------------------
def test_publish_disconnected_401(s, mongo):
    mongo.youtube_auth.delete_many({})
    r = s.post(f"{API}/youtube/publish", json={
        "filename": "final_x.mp4",
        "title": "test",
        "description": "",
        "tags": [],
        "privacy": "public",
    })
    assert r.status_code == 401
    assert "YouTube not connected" in r.json().get("detail", "")


# 4) privacy validation (must inject token so publish reaches privacy check) -
def test_publish_bad_privacy_400(s, mongo):
    mongo.youtube_auth.replace_one(
        {"_id": "primary"},
        {"_id": "primary", "refresh_token": "FAKE_TOKEN_FOR_TEST", "scope": "x"},
        upsert=True,
    )
    try:
        r = s.post(f"{API}/youtube/publish", json={
            "filename": "final_x.mp4",
            "title": "test",
            "privacy": "garbage",
        })
        assert r.status_code == 400
        assert "privacy" in r.json().get("detail", "").lower()
    finally:
        mongo.youtube_auth.delete_many({})


# 5) traversal guard — path stripped, then 404 ------------------------------
def test_publish_traversal_returns_404(s, mongo):
    mongo.youtube_auth.replace_one(
        {"_id": "primary"},
        {"_id": "primary", "refresh_token": "FAKE_TOKEN_FOR_TEST", "scope": "x"},
        upsert=True,
    )
    try:
        r = s.post(f"{API}/youtube/publish", json={
            "filename": "../../etc/passwd",
            "title": "test",
            "privacy": "public",
        })
        assert r.status_code == 404, f"got {r.status_code} {r.text}"
    finally:
        mongo.youtube_auth.delete_many({})


# 6) mp3 rejected — need a real existing mp3 --------------------------------
def test_publish_non_mp4_returns_400(s, mongo):
    # Find an existing mp3
    mp3s = [f for f in os.listdir(MEDIA_DIR) if f.endswith(".mp3")]
    assert mp3s, "no mp3 seed file in studio media"
    mongo.youtube_auth.replace_one(
        {"_id": "primary"},
        {"_id": "primary", "refresh_token": "FAKE_TOKEN_FOR_TEST", "scope": "x"},
        upsert=True,
    )
    try:
        r = s.post(f"{API}/youtube/publish", json={
            "filename": mp3s[0],
            "title": "test",
            "privacy": "public",
        })
        assert r.status_code == 400
        assert ".mp4" in r.json().get("detail", "")
    finally:
        mongo.youtube_auth.delete_many({})


# 7) job lookup 404 ---------------------------------------------------------
def test_publish_job_not_found(s):
    r = s.get(f"{API}/youtube/publish/does-not-exist")
    assert r.status_code == 404
