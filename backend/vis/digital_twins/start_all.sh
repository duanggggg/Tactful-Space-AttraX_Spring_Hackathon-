#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_LOG="$ROOT_DIR/mock_backend/backend.log"

cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

"$ROOT_DIR/start_backend.sh" >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

sleep 2

echo "Backend started on http://127.0.0.1:8787 (log: $BACKEND_LOG)"
echo "Starting frontend on http://127.0.0.1:5173"

"$ROOT_DIR/start_frontend.sh"
