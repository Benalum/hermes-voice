# Hermes Voice rough setup guide — macOS on Apple Silicon

> **Important:** This is a rough guide and will probably need refinement for the exact macOS version, Apple Silicon generation, browser, microphone permissions, package versions, and launchd environment. Dependency resolution for Apple Silicon has been validated, but the complete microphone, MLX, playback, Telegram, and launchd path still needs broader testing on real Macs.

## What this guide installs

- Hermes Agent with a Telegram gateway
- Hermes Voice from the `feature/telegram-chat-topics` branch
- Silero VAD
- Parakeet MLX speech-to-text
- Kokoro MLX text-to-speech
- A Telegram user session used by Hermes Voice
- An optional launchd agent

The conversation path is:

```text
Browser microphone
→ local Parakeet MLX
→ selected Telegram topic
→ Hermes Agent
→ reply in the same topic
→ local Kokoro MLX
→ browser speaker
```

Telegram stores topic names and message history. Hermes Voice does not create a separate chat-history database.

## 1. Confirm Apple Silicon

```bash
uname -m
```

Expected:

```text
arm64
```

If the result is `x86_64`, use the Intel macOS guide instead.

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

Install Git and FFmpeg through Homebrew when they are not already available:

```bash
brew install git ffmpeg
```

If Homebrew is not installed, install it first using its official instructions.

## 3. Install and verify Hermes Agent

Install Hermes Agent:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source "$HOME/.zshrc"
```

Configure a provider/model:

```bash
hermes setup
```

Verify a normal chat:

```bash
hermes
```

Do not add Telegram or Voice until a basic Hermes terminal conversation succeeds.

## 4. Configure the Hermes Agent Telegram bot

Create a bot with the official `@BotFather` and keep its token private.

Run:

```bash
hermes gateway setup
```

Select Telegram and provide the BotFather token.

Install and start the gateway:

```bash
hermes gateway install
hermes gateway start
hermes gateway status
```

View logs:

```bash
tail -f "$HOME/.hermes/logs/gateway.log"
```

### Enable Telegram topics

In BotFather, enable **Threaded Mode** for the Hermes bot. Allow the user to create/manage topics unless the deployment intentionally forbids it.

Open the private bot chat, create at least one topic, send a test message, and confirm Hermes replies in the same topic.

## 5. Get Telegram user API credentials

Create credentials at:

```text
https://my.telegram.org/apps
```

Record the numeric `api_id` and `api_hash`. These are separate from the BotFather bot token.

## 6. Clone and install Hermes Voice

```bash
cd "$HOME"

git clone \
  --branch feature/telegram-chat-topics \
  https://github.com/Benalum/hermes-voice.git

cd "$HOME/hermes-voice"

uv sync --extra speech --group dev
```

Confirm the MLX backend was selected:

```bash
uv run python - <<'PY'
from hermes_voice.io.speech_factory import detect_speech_backend
print(detect_speech_backend())
PY
```

Expected:

```text
mlx
```

Do not force `HV_SPEECH_BACKEND=portable` unless you are diagnosing an MLX-specific problem.

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

Find the correct absolute home path:

```bash
echo "$HOME"
```

Protect the config:

```bash
chmod 600 "$HOME/.hermes-voice/config.toml"
```

## 8. Authorize the Telegram user session

```bash
cd "$HOME/hermes-voice"

uv run python -m hermes_voice.scripts.login
```

Complete the phone, login-code, and optional two-factor prompts.

Then:

```bash
chmod 600 "$HOME/.hermes-voice/hermes.session"*
```

## 9. Validate the project

```bash
cd "$HOME/hermes-voice"

uv run ruff check .
uv run mypy --no-incremental hermes_voice
uv run pytest -q
node --check hermes_voice/web/main.js
```

The Node command is a developer syntax check. Install Node.js or omit only that check if Node is unavailable.

Optional model tests:

```bash
uv run pytest -m models
```

## 10. Start Hermes Voice manually

```bash
cd "$HOME/hermes-voice"

export HV_MODE=telegram
export HV_SPEECH_BACKEND=auto

uv run uvicorn hermes_voice.server.app:create_app \
  --factory \
  --host 127.0.0.1 \
  --port 8990
```

First startup can take longer while MLX speech models download and warm up.

In another terminal:

```bash
curl -sS http://127.0.0.1:8990/healthz
```

Open:

```text
http://127.0.0.1:8990/
```

Then:

1. Press **Start**.
2. Allow microphone access.
3. Select a Telegram topic.
4. Speak a test message.
5. Confirm the message and reply stay in the selected topic.
6. Confirm local speech playback.
7. Test **Stop Speech**.
8. Test **Immersion**.
9. Search for part of a topic title.

## 11. Install a launchd agent

First prove manual startup works. Then stop the manual server.

Create a log directory:

```bash
mkdir -p "$HOME/.hermes-voice/logs"
```

Create a plist, replacing `YOUR_USERNAME` in every absolute path:

```bash
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

Validate and load:

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

Follow logs:

```bash
tail -f "$HOME/.hermes-voice/logs/server-error.log"
```

This launchd section is especially likely to need refinement. macOS launchd uses static paths and a restricted environment. Recreate or edit the plist if the repository, Python environment, or username changes.

## Troubleshooting

### WebSocket connection failed

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8990/

launchctl print "gui/$(id -u)/com.hermes.voice"
tail -n 200 "$HOME/.hermes-voice/logs/server-error.log"
```

### Port 8990 is occupied

```bash
lsof -nP -iTCP:8990 -sTCP:LISTEN
```

### Backend is not MLX

```bash
uname -m

uv run python - <<'PY'
from hermes_voice.io.speech_factory import detect_speech_backend
print(detect_speech_backend())
PY
```

Apple Silicon should report `arm64` and `mlx`.

### Topics do not appear

- Confirm Threaded Mode is enabled.
- Create at least one topic in Telegram.
- Confirm the configured bot username.
- Press **Refresh**.
- Re-run the login script.

### Topic search behavior

Topic search matches title words locally in the browser. It does not search message contents.

### Microphone or speaker is blocked

- Check System Settings → Privacy & Security → Microphone.
- Allow microphone access for the browser.
- Check the browser site permission for localhost.
- Test Chrome and Safari separately.
- Confirm the correct speaker output device.

### MLX import or model errors

```bash
uv sync --extra speech --group dev

uv run python -c \
  "from hermes_voice.io.speech_factory import detect_speech_backend; print(detect_speech_backend())"
```

Capture the complete error before changing package versions.

### Security reminders

- Never commit `config.toml` or `hermes.session`.
- Keep both mode `600`.
- Keep the BotFather token, `api_hash`, and browser token private.
- Bind to localhost unless using a secure tunnel or private proxy.
