#!/usr/bin/env bash
# Sentinel: one command, fully local/offline after first install.
# Usage: ./start.sh            (API :8000, UI :5173; override with API_PORT / WEB_PORT)
set -euo pipefail
cd "$(dirname "$0")"
API_PORT="${API_PORT:-8000}"; WEB_PORT="${WEB_PORT:-5173}"
PY=python3; command -v $PY >/dev/null || PY=python
VENV_BIN=backend/.venv/bin; [ -d backend/.venv/Scripts ] && VENV_BIN=backend/.venv/Scripts

if [ ! -d backend/.venv ]; then
  echo "[sentinel] creating Python venv…"; $PY -m venv backend/.venv
  "$VENV_BIN/python" -m pip install -q -r backend/requirements.txt
fi
[ -d frontend/node_modules ] || (echo "[sentinel] installing frontend deps…"; cd frontend && npm install --silent)

echo "[sentinel] API  → http://127.0.0.1:$API_PORT   (warms the demo; builds the eval report on first run)"
(cd backend && "../$VENV_BIN/python" -m uvicorn app.main:app --port "$API_PORT") &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM
echo "[sentinel] UI   → http://localhost:$WEB_PORT"
cd frontend && SENTINEL_API="http://127.0.0.1:$API_PORT" npx vite --port "$WEB_PORT" --strictPort
