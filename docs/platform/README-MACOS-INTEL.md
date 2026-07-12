# Hermes Voice rough setup guide — macOS on Intel

> **Important:** This is a rough guide and will probably need refinement for the exact Intel Mac, macOS version, browser, microphone permissions, Python wheels, speech-model performance, and launchd environment. Dependency resolution for Intel macOS has been validated, but the complete speech and launchd path still needs broader testing on real Intel Macs.

## What this guide installs

- Hermes Agent with a Telegram gateway
- Hermes Voice from the `feature/telegram-chat-topics` branch
- Silero VAD
- Faster-Whisper speech-to-text
- Portable Kokoro text-to-speech
- A Telegram user session used by Hermes Voice
- An optional launchd agent

The conversation path is:

```text
Browser microphone
→ local Faster-Whisper
→ selected Telegram topic
→ Hermes Agent
→ reply in the same topic
→ local portable Kokoro
→ browser speaker
```

Telegram stores topic names and message history. Hermes Voice does not create a separate chat-history database.

## 1. Confirm Intel architecture

```bash
uname -m
```

Expected:

```text
x86_64
```

If the result is `arm64`, use the Apple Silicon guide.

## 2. Install command-line prerequisites

Install Apple Command Line Tools:

```bash
xcode-select --install
```

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reload the shell:

```bash
source "$HOME/.local/bin/env" 2>/dev/null || true
hash -r

uv --version
```

Install Python 3.12:

```bash
uv python install 3.12
```

Install Git and FFmpeg through Homebrew when needed:

```bash
brew install git ffmpeg
```

## 3. Install and verify Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source "$HOME/.zshrc"

hermes setup
hermes
```

Do not continue until Hermes responds correctly in a normal terminal chat.

## 4. Configure the Hermes Agent Telegram bot

Create the bot through the official `@BotFather`, then run:

```bash
hermes gateway setup
hermes gateway install
hermes gateway start
hermes gateway status
```

View logs:

```bash
tail -f "$HOME/.hermes/logs/gateway.log"
```

### Enable Telegram topics

In Telegram, use this BotFather path:

```text
@BotFather
→ select the Hermes bot
→ Bot Settings
→ Thread Settings
→ enable Threaded Mode
```

Allow the user to create and manage topics unless intentionally restricted. Telegram may change the exact menu wording; the required result is private-chat topic/thread mode for the bot.

The BotFather token belongs to Hermes Agent and is entered during `hermes gateway setup`. Do **not** put it in `~/.hermes-voice/config.toml`.

Create at least one topic in the private Hermes bot chat. Send a message and confirm Hermes replies in that same topic.

## 5. Get Telegram user API credentials

Create credentials at:

```text
https://my.telegram.org/apps
```

Record the numeric `api_id` and `api_hash`.

The values are used as follows:

```text
BotFather bot token
→ hermes gateway setup

Telegram api_id and api_hash
→ ~/.hermes-voice/config.toml under [telegram]

Hermes bot username
→ ~/.hermes-voice/config.toml as chats.hermes.peer

Hermes Voice browser/gateway token
→ ~/.hermes-voice/config.toml as the top-level token
```

## 6. Clone and install Hermes Voice

```bash
cd "$HOME"

git clone \
  --branch feature/telegram-chat-topics \
  https://github.com/Benalum/hermes-voice.git

cd "$HOME/hermes-voice"

uv sync --extra speech --group dev
```

Confirm the portable backend:

```bash
uv run python - <<'PY'
from hermes_voice.io.speech_factory import detect_speech_backend
print(detect_speech_backend())
PY
```

Expected:

```text
portable
```

Intel macOS does not use the MLX backend. Do not set `HV_SPEECH_BACKEND=mlx`.

## 7. Create the Hermes Voice configuration

```bash
mkdir -p "$HOME/.hermes-voice"
chmod 700 "$HOME/.hermes-voice"
```

Generate a browser token:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
```

Create:

```bash
nano "$HOME/.hermes-voice/config.toml"
```

Template:

```toml
token = "REPLACE_WITH_THE_RANDOM_BROWSER_TOKEN"

[telegram]
api_id = 12345678
api_hash = "REPLACE_WITH_TELEGRAM_API_HASH"
session_path = "/Users/YOUR_USERNAME/.hermes-voice/hermes.session"

[chats.hermes]
peer = "@YOUR_HERMES_BOT_USERNAME"
label = "Hermes"
max_wait_s = 180
```

Use the real absolute path from:

```bash
echo "$HOME"
```

Protect the config:

```bash
chmod 600 "$HOME/.hermes-voice/config.toml"
```

### Find the gateway token later

The browser prompt labeled **Gateway token** uses the top-level `token` from this file. It is not the BotFather bot token and it is not the old Hermes RPC session token.

Display it when connecting a new phone or browser:

```bash
python3 - <<'PY'
from pathlib import Path
import tomllib

path = Path.home() / ".hermes-voice" / "config.toml"
with path.open("rb") as handle:
    config = tomllib.load(handle)

token = config.get("token")
if not token:
    raise SystemExit(f"No top-level token found in {path}")

print(token)
PY
```

Keep the printed value private.

## 8. Authorize the Telegram user session

```bash
cd "$HOME/hermes-voice"

uv run python -m hermes_voice.scripts.login

chmod 600 "$HOME/.hermes-voice/hermes.session"*
```

## 9. Validate

```bash
cd "$HOME/hermes-voice"

uv run ruff check .
uv run mypy --no-incremental hermes_voice
uv run pytest -q
node --check hermes_voice/web/main.js
```

Optional model tests:

```bash
uv run pytest -m models
```

The Node command is only a developer JavaScript syntax check.

## 10. Start manually

```bash
cd "$HOME/hermes-voice"

export HV_MODE=telegram
export HV_SPEECH_BACKEND=auto

uv run uvicorn hermes_voice.server.app:create_app \
  --factory \
  --host 127.0.0.1 \
  --port 8990
```

First startup may take time while the portable speech stack downloads models and warms up.

Check health:

```bash
curl -sS http://127.0.0.1:8990/healthz
```

Open:

```text
http://127.0.0.1:8990/
```

Test:

1. Start and grant microphone access.
2. Select a Telegram topic.
3. Speak a short request.
4. Confirm it is appended to the selected topic.
5. Confirm the reply remains in that topic.
6. Confirm local TTS playback.
7. Test Stop Speech, topic search, and Immersion.

## 11. Optional launchd service

Stop the manual server and create:

```bash
mkdir -p "$HOME/.hermes-voice/logs"

cat > "$HOME/Library/LaunchAgents/com.hermes.voice.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.hermes.voice</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOUR_USERNAME/hermes-voice/.venv/bin/uvicorn</string>
    <string>hermes_voice.server.app:create_app</string>
    <string>--factory</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>8990</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/YOUR_USERNAME/hermes-voice</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>HV_MODE</key>
    <string>telegram</string>
    <key>HV_SPEECH_BACKEND</key>
    <string>auto</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>/Users/YOUR_USERNAME/.hermes-voice/logs/server.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOUR_USERNAME/.hermes-voice/logs/server-error.log</string>
</dict>
</plist>
PLIST
```

Replace `YOUR_USERNAME` in every path, then:

```bash
plutil -lint "$HOME/Library/LaunchAgents/com.hermes.voice.plist"

launchctl bootout \
  "gui/$(id -u)/com.hermes.voice" \
  2>/dev/null || true

launchctl bootstrap \
  "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.hermes.voice.plist"

launchctl kickstart -k \
  "gui/$(id -u)/com.hermes.voice"

launchctl print \
  "gui/$(id -u)/com.hermes.voice"
```

Logs:

```bash
tail -f "$HOME/.hermes-voice/logs/server-error.log"
```

This launchd setup is a rough template. Static paths, restricted service environments, and Intel-specific package behavior may require adjustments.

## 12. Use from a phone or another device with Tailscale

Keep Uvicorn bound to `127.0.0.1`. Install the Tailscale app on the Mac and on the phone, tablet, or second computer, then join both devices to the same tailnet.

Confirm the local service and Tailscale connection:

```bash
curl -sS http://127.0.0.1:8990/healthz
tailscale status
```

Publish Hermes Voice privately:

```bash
tailscale serve --bg 8990
tailscale serve status
```

If the CLI reports a permissions error, retry with `sudo`. If `tailscale` is not in the shell path, install or update the Tailscale app and enable its command-line integration.

Tailscale prints a private HTTPS address similar to:

```text
https://hermes.example-tailnet.ts.net
```

On the other device:

1. Turn on Tailscale.
2. Open the printed HTTPS address.
3. Enter the Hermes Voice gateway token from the top-level `token` in `~/.hermes-voice/config.toml`.
4. Grant microphone permission.
5. Select a Telegram topic and press **Start**.

HTTPS is important for browser microphone permission and secure WebSockets. Use **Tailscale Serve**, not **Tailscale Funnel**, unless public Internet exposure is intentionally desired.

Remove the private Serve mapping with:

```bash
tailscale serve reset
```

## Troubleshooting

### WebSocket connection failed

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8990/

launchctl print "gui/$(id -u)/com.hermes.voice"
tail -n 200 "$HOME/.hermes-voice/logs/server-error.log"
```

### Tailscale URL does not open

```bash
tailscale status
tailscale serve status
curl -sS http://127.0.0.1:8990/healthz
```

Confirm the client device is connected to the same tailnet. Re-run `tailscale serve --bg 8990` if the mapping is absent.

### Port conflict

```bash
lsof -nP -iTCP:8990 -sTCP:LISTEN
```

### Wrong backend

```bash
uname -m

uv run python - <<'PY'
from hermes_voice.io.speech_factory import detect_speech_backend
print(detect_speech_backend())
PY
```

Intel macOS should report `x86_64` and `portable`.

### Portable speech is too slow or consumes too much memory

Start with short prompts and the default configuration. Capture CPU, memory, and full logs before changing model sizes. Older Intel Macs may need smaller STT models or additional performance tuning; this guide does not yet prescribe one universal setting.

### Topics do not appear

- Enable Threaded Mode.
- Create a topic.
- Verify the bot username in `config.toml`.
- Press Refresh.
- Re-run the login script.

### Search does not find a topic

Search matches title words locally and does not search message bodies. Refresh after creating or renaming a topic.

### Microphone permission

Check System Settings → Privacy & Security → Microphone and the browser's site permissions.

### Security reminders

- Never commit `config.toml` or `hermes.session`.
- Keep both mode `600`.
- Keep the BotFather token, Telegram API hash, and browser token private.
- Keep Uvicorn bound to localhost unless protected by a secure private-access layer.
