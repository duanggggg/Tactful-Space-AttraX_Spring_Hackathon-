#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PARENT="$(cd "$ROOT_DIR/.." && pwd)"
OUTPUT_DIR="${1:-$PROJECT_PARENT}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BUNDLE_NAME="digital_twins_offline_bundle_${STAMP}.tar.gz"
BUNDLE_PATH="$OUTPUT_DIR/$BUNDLE_NAME"

mkdir -p "$OUTPUT_DIR"

cd "$PROJECT_PARENT"

tar \
  --exclude="digital_twins/frontend/node_modules/.cache" \
  --exclude="digital_twins/frontend/dist/.vite" \
  -czf "$BUNDLE_PATH" \
  digital_twins

echo "Offline bundle created:"
echo "$BUNDLE_PATH"
