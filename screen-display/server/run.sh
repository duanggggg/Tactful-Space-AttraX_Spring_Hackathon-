#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SERVER_DIR/../.." && pwd)"
VENV_PY="$REPO_ROOT/backend/.venv/Scripts/python.exe"

if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$REPO_ROOT/backend/.venv/bin/python"
fi

if [[ ! -x "$VENV_PY" ]]; then
  echo "[error] backend venv python not found; run uv venv in backend/ first." >&2
  exit 1
fi

cd "$SERVER_DIR"
exec "$VENV_PY" -m uvicorn save_layout:app --host 127.0.0.1 --port 8788 --reload
