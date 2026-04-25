#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/.run_logs"
VIS_BACKEND_DIR="$ROOT_DIR/backend/vis/digital_twins/mock_backend"
VIS_FRONTEND_DIR="$ROOT_DIR/backend/vis/digital_twins/frontend"
MCP_DIR="$ROOT_DIR/mcp"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"

VIS_BACKEND_LOG="$LOG_DIR/vis_backend_${TIMESTAMP}.log"
VIS_FRONTEND_LOG="$LOG_DIR/vis_frontend_${TIMESTAMP}.log"
DEVICE_LLM_LOG="$LOG_DIR/device_llm_server_${TIMESTAMP}.log"
MCP_LOG="$LOG_DIR/mcp_pipe_${TIMESTAMP}.log"

PIDS=()

mkdir -p "$LOG_DIR"

find_conda_sh() {
  local candidates=()

  if [[ -n "${CONDA_EXE:-}" ]]; then
    candidates+=("$(cd "$(dirname "$CONDA_EXE")/.." && pwd)/etc/profile.d/conda.sh")
  fi

  candidates+=(
    "$HOME/opt/anaconda3/etc/profile.d/conda.sh"
    "$HOME/anaconda3/etc/profile.d/conda.sh"
    "/opt/anaconda3/etc/profile.d/conda.sh"
    "/usr/local/anaconda3/etc/profile.d/conda.sh"
  )

  local path
  for path in "${candidates[@]}"; do
    if [[ -f "$path" ]]; then
      echo "$path"
      return 0
    fi
  done

  return 1
}

cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-40}"
  local delay="${4:-1}"
  local i

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[ok] $name is ready: $url"
      return 0
    fi
    sleep "$delay"
  done

  echo "[warn] $name did not become ready in time: $url"
  return 1
}

start_process() {
  local name="$1"
  local workdir="$2"
  local logfile="$3"
  shift 3

  (
    cd "$workdir"
    "$@" >"$logfile" 2>&1
  ) &

  local pid=$!
  PIDS+=("$pid")
  echo "[start] $name (pid=$pid, log=$logfile)"
}

require_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "[error] Missing required path: $path"
    exit 1
  fi
}

trap cleanup EXIT INT TERM

require_path "$VIS_BACKEND_DIR/app.py"
require_path "$VIS_FRONTEND_DIR/package.json"
require_path "$MCP_DIR/mcp_pipe.py"
require_path "$MCP_DIR/device_llm_server.py"

if [[ -z "${MCP_ENDPOINT:-}" && ! -f "$MCP_DIR/.env" ]]; then
  echo "[error] MCP_ENDPOINT is not set, and $MCP_DIR/.env was not found."
  echo "        Export MCP_ENDPOINT first, then rerun this script."
  exit 1
fi

if ! CONDA_SH="$(find_conda_sh)"; then
  echo "[error] Could not find conda.sh. Please check your Anaconda installation."
  exit 1
fi

source "$CONDA_SH"
conda activate py312

export PYTHONUNBUFFERED=1
export MCP_CONFIG="${MCP_CONFIG:-$MCP_DIR/mcp_config.json}"

if ! command -v python >/dev/null 2>&1; then
  echo "[error] python is unavailable after activating py312."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] npm is not installed or not in PATH."
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "[error] curl is not installed or not in PATH."
  exit 1
fi

if [[ ! -d "$VIS_FRONTEND_DIR/node_modules" ]]; then
  echo "[info] frontend/node_modules is missing. Running npm install once..."
  (
    cd "$VIS_FRONTEND_DIR"
    npm install
  )
fi

echo "[info] Using python: $(command -v python)"
echo "[info] Using node: $(command -v npm)"
echo "[info] Logs directory: $LOG_DIR"

start_process "visualization backend" "$VIS_BACKEND_DIR" "$VIS_BACKEND_LOG" python -m uvicorn app:app --host 0.0.0.0 --port 8787
wait_for_http "visualization backend" "http://127.0.0.1:8787/api/v1/health" 30 1 || true

start_process "device llm server" "$MCP_DIR" "$DEVICE_LLM_LOG" python device_llm_server.py
wait_for_http "device llm server" "http://127.0.0.1:12345/health" 30 1 || true

start_process "mcp pipe" "$MCP_DIR" "$MCP_LOG" python mcp_pipe.py
sleep 3

start_process "visualization frontend" "$VIS_FRONTEND_DIR" "$VIS_FRONTEND_LOG" npm run dev -- --host 0.0.0.0 --port 5173
wait_for_http "visualization frontend" "http://127.0.0.1:5173" 40 1 || true

echo
echo "Services started."
echo "  Visualization frontend: http://127.0.0.1:5173"
echo "  Visualization backend : http://127.0.0.1:8787"
echo "  Device LLM server     : http://127.0.0.1:12345/health"
echo "  MCP log               : $MCP_LOG"
echo
echo "Press Ctrl+C to stop all services."

wait
