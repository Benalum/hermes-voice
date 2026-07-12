# Hermes Voice rough setup guide — Ubuntu / Linux

> **Important:** This is a rough guide, not finalized production documentation. It has been exercised most thoroughly on Ubuntu 24.04, but package names, audio behavior, browser permissions, service setup, and model compatibility may differ on other Linux distributions. Expect to refine it for the target machine.

## What this guide installs

- Hermes Agent with a Telegram gateway
- Hermes Voice from the `feature/telegram-chat-topics` branch
- Silero VAD
- Faster-Whisper speech-to-text
- Portable Kokoro text-to-speech
- A Telegram user session used by Hermes Voice
- An optional user-level systemd service

The conversation path is:

```text
Browser microphone
→ local Faster-Whisper
→ selected Telegram topic
→ Hermes Agent
→ reply in the same topic
→ local Kokoro
→ browser speaker
```

Telegram stores topic names and message history. Hermes Voice does not create a separate chat-history database.

## 1. Install basic operating-system packages

```bash
sudo apt update

sudo apt install -y \
  build-essential \
  curl \
  ffmpeg \
  git \
  libsndfile1 \
  python3-dev
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

Install the project Python version:

```bash
uv python install 3.12
```

## 2. Install and verify Hermes Agent

Install Hermes Agent:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source "$HOME/.bashrc"
```

Run the setup wizard and select a model/provider:

```bash
hermes setup
```

Verify a normal terminal conversation works:

```bash
hermes
```

Do not continue until Hermes can answer a basic terminal prompt.

## 3. Create and configure the Hermes Telegram bot

In Telegram:

1. Open the official `@BotFather`.
2. Create a bot with `/newbot`.
3. Keep the bot token private.
4. Run the Hermes messaging setup:

```bash
hermes gateway setup
```

Select Telegram and provide the BotFather token.

Install and start the Hermes Agent gateway:

```bash
hermes gateway install
hermes gateway start
hermes gateway status
```

View gateway logs when needed:

```bash
journalctl --user -u hermes-gateway -f
```

### Enable Telegram topics

In BotFather, open the bot settings and enable **Threaded Mode**. Allow the user to create/manage topics unless the deployment intentionally forbids it.

Open the private chat with the Hermes bot and create at least one topic, for example:

```text
General
```

Send a message in that topic and confirm Hermes replies in the same topic.

## 4. Get Telegram user API credentials

Hermes Voice uses a Telethon **user session** in addition to the Hermes Agent bot token.

Create Telegram API credentials at:

```text
https://my.telegram.org/apps
```

Record the numeric `api_id` and the `api_hash`. Do not commit them.

## 5. Clone Hermes Voice

```bash
cd "$HOME"

git clone \
  --branch feature/telegram-chat-topics \
  https://github.com/Benalum/hermes-voice.git

cd "$HOME/hermes-voice"
```

Install the platform-selected speech dependencies and development tools:

```bash
uv sync --extra speech --group dev
```

Confirm Linux selected the portable backend:

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

## 6. Create the Hermes Voice configuration

Create the configuration directory:

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

Create the config:

```bash
nano "$HOME/.hermes-voice/config.toml"
```

Use this structure and replace every placeholder:

```toml
token = "REPLACE_WITH_THE_RANDOM_BROWSER_TOKEN"

[telegram]
api_id = 12345678
api_hash = "REPLACE_WITH_TELEGRAM_API_HASH"
session_path = "/home/YOUR_USERNAME/.hermes-voice/hermes.session"

[chats.hermes]
peer = "@YOUR_HERMES_BOT_USERNAME"
label = "Hermes"
max_wait_s = 180
```

Use the real absolute home path:

```bash
echo "$HOME"
```

Protect the config:

```bash
chmod 600 "$HOME/.hermes-voice/config.toml"
```

## 7. Authorize the Telegram user session

```bash
cd "$HOME/hermes-voice"

uv run python -m hermes_voice.scripts.login
```

Telegram may request:

- phone number
- login code
- two-factor authentication password

After login, protect the session file:

```bash
chmod 600 "$HOME/.hermes-voice/hermes.session"*
```

The login command should also confirm that the configured Hermes bot peer resolves.

## 8. Run validation

```bash
cd "$HOME/hermes-voice"

uv run ruff check .
uv run mypy --no-incremental hermes_voice
uv run pytest -q
node --check hermes_voice/web/main.js
```

The Node command is a developer syntax check. Install Node.js or omit only that check if Node is not available.

Optional model tests:

```bash
uv run pytest -m models
```

## 9. Start Hermes Voice manually

```bash
cd "$HOME/hermes-voice"

export HV_MODE=telegram
export HV_SPEECH_BACKEND=auto

uv run uvicorn hermes_voice.server.app:create_app \
  --factory \
  --host 127.0.0.1 \
  --port 8990
```

First startup can take longer while speech models download and warm up.

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
2. Allow browser microphone access.
3. Select a Telegram topic.
4. Speak a test message.
5. Confirm the text appears in that Telegram topic.
6. Confirm Hermes replies in the same topic.
7. Confirm the reply is spoken locally.
8. Test **Stop Speech**.
9. Test **Immersion**.
10. Search for part of a topic title.

## 10. Install Hermes Voice as a user systemd service

Stop the manually running server first.

Create the unit:

```bash
mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/.config/systemd/user/hermes-voice.service" <<'UNIT'
[Unit]
Description=Hermes Voice
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/hermes-voice
Environment=HV_MODE=telegram
Environment=HV_SPEECH_BACKEND=auto
ExecStart=%h/hermes-voice/.venv/bin/uvicorn hermes_voice.server.app:create_app --factory --host 127.0.0.1 --port 8990
Restart=on-failure
RestartSec=5
TimeoutStartSec=0

[Install]
WantedBy=default.target
UNIT
```

Enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now hermes-voice
systemctl --user status hermes-voice
```

Follow logs:

```bash
journalctl --user -u hermes-voice -f
```

For a headless VM that must survive logout and start at boot:

```bash
sudo loginctl enable-linger "$USER"
```

## 11. Remote browser access

Keep Uvicorn bound to `127.0.0.1`. Do not expose port `8990` directly to the public Internet.

Use one of:

- an SSH tunnel
- Tailscale
- a private authenticated reverse proxy with TLS

Example SSH tunnel from another computer:

```bash
ssh -L 8990:127.0.0.1:8990 YOUR_USER@YOUR_HERMES_HOST
```

Then open `http://127.0.0.1:8990/` on the client computer.

## Troubleshooting

### WebSocket connection failed

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8990/

systemctl --user status hermes-voice
journalctl --user -u hermes-voice -n 200 --no-pager
```

### Port 8990 is already in use

```bash
ss -ltnp | grep ':8990' || true
fuser -v -n tcp 8990 || true
```

### Topics do not appear

- Confirm the bot has Threaded Mode enabled.
- Confirm at least one topic exists.
- Confirm the configured `peer` is the correct bot.
- Press **Refresh**.
- Re-run the Telegram login script.

### Topic search returns no matches

Search matches topic **titles**, not message contents. It uses case-insensitive word matching in the browser. Press **Refresh** if a topic was recently created or renamed.

### Microphone does not work

- Allow microphone permission for `127.0.0.1`.
- Check the browser site permissions.
- Try Chrome or Chromium.
- Confirm the page is opened through localhost, an SSH tunnel, or HTTPS.

### Startup seems stuck

First startup may be loading Faster-Whisper, Kokoro, Silero, spaCy, or model files. Follow the service logs and allow time for downloads.

### Security reminders

- Never commit `config.toml`.
- Never commit `hermes.session`.
- Keep both files mode `600`.
- Keep the browser token private.
- Keep the BotFather token and Telegram API hash private.
- Bind to localhost unless a secure private-access layer is configured.
