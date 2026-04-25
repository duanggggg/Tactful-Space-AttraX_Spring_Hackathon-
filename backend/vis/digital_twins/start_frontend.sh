#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  echo "Missing frontend dependencies: $FRONTEND_DIR/node_modules"
  echo "Run npm install on an online machine first, then repackage."
  exit 1
fi

exec npm run dev -- --host 0.0.0.0 --port 5173
