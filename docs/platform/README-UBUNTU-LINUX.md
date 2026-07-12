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

In Telegram, use this BotFather path:

```text
@BotFather
→ select the Hermes bot
→ Bot Settings
→ Thread Settings
→ enable Threaded Mode
```

Allow the user to create and manage topics unless the deployment intentionally forbids it. Telegram may change the exact menu wording; the required result is private-chat topic/thread mode for the bot.

The BotFather token is used by Hermes Agent through `hermes gateway setup`. Do **not** put the BotFather token in `~/.hermes-voice/config.toml`.

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

## 11. Use from a phone or another device with Tailscale

Keep Uvicorn bound to `127.0.0.1`. Do not expose port `8990` directly to the public Internet.

Install Tailscale on the Hermes Voice host and on the phone, tablet, or second computer. Join both devices to the same tailnet.

Confirm the server is healthy:

```bash
curl -sS http://127.0.0.1:8990/healthz
tailscale status
```

Publish the localhost service privately:

```bash
sudo tailscale serve --bg 8990
sudo tailscale serve status
```

Tailscale prints a private HTTPS address similar to:

```text
https://hermes.example-tailnet.ts.net
```

On the other device:

1. Turn on Tailscale.
2. Open the printed HTTPS address in the browser.
3. Enter the Hermes Voice gateway token from the top-level `token` in `~/.hermes-voice/config.toml`.
4. Grant microphone permission.
5. Select a Telegram topic and press **Start**.

HTTPS is important because phone browsers normally require a secure context for microphone access and secure WebSockets.

Use **Tailscale Serve**, not **Tailscale Funnel**, unless public Internet exposure is intentionally desired.

To remove the Serve configuration:

```bash
sudo tailscale serve reset
```

An SSH tunnel remains a useful desktop alternative:

```bash
ssh -L 8990:127.0.0.1:8990 YOUR_USER@YOUR_HERMES_HOST
```

Then open `http://127.0.0.1:8990/` on that desktop computer.

## Troubleshooting

### WebSocket connection failed

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' \
  http://127.0.0.1:8990/

systemctl --user status hermes-voice
journalctl --user -u hermes-voice -n 200 --no-pager
```

### Tailscale URL does not open

```bash
tailscale status
sudo tailscale serve status
curl -sS http://127.0.0.1:8990/healthz
```

Confirm the client device is connected to the same tailnet. Re-run `sudo tailscale serve --bg 8990` if the mapping is absent.

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
