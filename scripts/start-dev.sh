#!/usr/bin/env bash

set -Eeuo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "API environment is missing. Run: make api-install" >&2
  exit 1
fi

child_pids=()

stop_services() {
  trap - EXIT INT TERM
  for child_pid in "${child_pids[@]}"; do
    kill "$child_pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

trap stop_services EXIT INT TERM

echo "Starting CALIBER API on http://localhost:8000"
.venv/bin/uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8000 &
child_pids+=("$!")

echo "Starting CALIBER web app on http://localhost:5173"
npm run dev --workspace=@caliber/web &
child_pids+=("$!")

wait -n "${child_pids[@]}"
