#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--dry-run]" >&2
  exit 2
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_PATH="$UNIT_DIR/hermes-voice.service"
UVICORN="$REPO/.venv/bin/uvicorn"

if [[ ! -x "$UVICORN" ]]; then
  echo "ERROR: missing $UVICORN; run uv sync first" >&2
  exit 1
fi

render() {
  cat <<EOF
[Unit]
Description=Hermes Voice Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=HV_MODE=telegram
Environment=HV_SPEECH_BACKEND=auto
Environment=HV_MAX_SPOKEN_CHARS=0
ExecStart=$UVICORN hermes_voice.server.app:create_app --factory --host 127.0.0.1 --port 8990
Restart=on-failure
RestartSec=5
TimeoutStartSec=0

[Install]
WantedBy=default.target
EOF
}

if $DRY_RUN; then
  echo "Would write: $UNIT_PATH"
  render
  exit 0
fi

mkdir -p "$UNIT_DIR"
render > "$UNIT_PATH"
systemctl --user daemon-reload
systemctl --user enable --now hermes-voice.service
systemctl --user status hermes-voice.service --no-pager
