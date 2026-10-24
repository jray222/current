#!/usr/bin/env bash
# Local development launcher: FastAPI backend (:5733) + Vite frontend (:5173).
# Works on Linux, macOS and Windows (Git Bash). For Docker, use `docker compose up`.
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND="$SCRIPT_DIR/backend"
VENV="$BACKEND/.venv"

if [ -x "$VENV/Scripts/python.exe" ]; then PY="$VENV/Scripts/python.exe"
elif [ -x "$VENV/bin/python" ]; then PY="$VENV/bin/python"
else
  echo "Creating Python virtual environment in backend/.venv ..."
  python3 -m venv "$VENV" 2>/dev/null || python -m venv "$VENV"
  if [ -x "$VENV/Scripts/python.exe" ]; then PY="$VENV/Scripts/python.exe"; else PY="$VENV/bin/python"; fi
  "$PY" -m pip install -q -r "$BACKEND/requirements.txt" -r "$BACKEND/requirements-dev.txt"
fi

if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
  echo "Installing frontend dependencies ..."
  (cd "$SCRIPT_DIR/frontend" && npm install --no-audit --no-fund)
fi

echo "Starting backend on http://localhost:5733 ..."
(cd "$BACKEND" && "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 5733 --reload) &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
(cd "$SCRIPT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
echo "--------------------------------------------------------"
echo "Dose is starting:  http://localhost:5173"
echo "API docs:            http://localhost:5733/docs"
echo "--------------------------------------------------------"
wait
