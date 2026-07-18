#!/bin/zsh
set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--dry-run]" >&2
  exit 2
fi

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.hermes.voice"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/hermes-voice"
UVICORN="$REPO/.venv/bin/uvicorn"

if [[ ! -x "$UVICORN" ]]; then
  echo "ERROR: missing $UVICORN; run uv sync first" >&2
  exit 1
fi

render() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$UVICORN</string>
    <string>hermes_voice.server.app:create_app</string>
    <string>--factory</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8990</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HV_MODE</key><string>telegram</string>
    <key>HV_SPEECH_BACKEND</key><string>auto</string>
    <key>HV_MAX_SPOKEN_CHARS</key><string>0</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/stdout.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/stderr.log</string>
</dict>
</plist>
EOF
}

if $DRY_RUN; then
  echo "Would write: $PLIST"
  render
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
render > "$PLIST"
plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
launchctl print "gui/$(id -u)/$LABEL"
