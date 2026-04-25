#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/mock_backend"
VENV_DIR="$BACKEND_DIR/.venv"

cd "$BACKEND_DIR"

if [ ! -d "$VENV_DIR" ]; then
  echo "Missing virtual environment: $VENV_DIR"
  echo "Run ./prepare_backend_venv.sh on an online machine first, then repackage."
  exit 1
fi

source "$VENV_DIR/bin/activate"
exec uvicorn app:app --host 0.0.0.0 --port 8787
