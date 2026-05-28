"""Shared conftest — loads env vars from /app/backend/.env and /app/frontend/.env
so tests can talk to MongoDB (for in-process tests) and to the public backend URL.
"""
import os
import pathlib
import sys


def _load_env(path: str):
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


_load_env("/app/backend/.env")
_load_env("/app/frontend/.env")

# Make /app/backend importable for direct module tests
sys.path.insert(0, "/app/backend")
