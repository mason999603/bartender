#!/usr/bin/env bash
# Convenience launcher — assumes you've followed README.md (venv at ./venv, voice at ./voices/...).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "No venv found. Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements_pi.txt"
  exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate
exec python russell_pi_client.py "$@"
