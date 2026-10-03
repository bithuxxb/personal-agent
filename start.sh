#!/usr/bin/env bash
# Personal Agent 启动脚本
#   ./start.sh       启动 Web UI（默认 http://127.0.0.1:8765）
#   ./start.sh cli   启动 CLI
set -euo pipefail

cd "$(dirname "$0")"
PYTHON=".venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 .venv，请先运行：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "未找到 .env，请先复制 .env.example 为 .env 并填入 LLM_API_KEY" >&2
  exit 1
fi

if [[ "${1:-web}" == "cli" ]]; then
  exec "$PYTHON" main.py
else
  HOST="${HOST:-127.0.0.1}"
  PORT="${PORT:-8765}"
  echo "Web UI 启动中：http://${HOST}:${PORT}"
  exec "$PYTHON" -m uvicorn web.server:app --host "$HOST" --port "$PORT"
fi
