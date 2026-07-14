
# Fresh install — Ubuntu 24.04 x64

This is the primary verified deployment path. Other Linux distributions may require different package names.

## 1. Install operating-system packages

```bash
sudo apt update
sudo apt install -y build-essential curl ffmpeg git libsndfile1 nodejs python3-dev unzip
```

Install `uv` and Python 3.12:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env" 2>/dev/null || true
uv python install 3.12
uv --version
```

## 2. Install and verify Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source "$HOME/.bashrc"
hermes setup
hermes
```

Do not continue until a normal terminal conversation succeeds.

Configure the Telegram gateway:

```bash
hermes gateway setup
hermes gateway install
hermes gateway start
hermes gateway status
```

Create the bot through `@BotFather`, enable private-chat threaded/topic mode, create at least one topic,
and verify that Hermes replies in that topic. The BotFather token belongs to Hermes Agent, not Hermes Voice.

## 3. Install Hermes Voice

```bash
cd "$HOME"
git clone https://github.com/Benalum/hermes-voice.git
cd "$HOME/hermes-voice"
uv sync --locked --extra speech --group dev
```

Verify the platform:

```bash
uv run python scripts/verify_platform.py --expected-backend portable
```

## 4. Create the Hermes Voice configuration

Create Telegram API credentials at `https://my.telegram.org/apps`, then run:

```bash
mkdir -p "$HOME/.hermes-voice"
chmod 700 "$HOME/.hermes-voice"
cp config.example.toml "$HOME/.hermes-voice/config.toml"
chmod 600 "$HOME/.hermes-voice/config.toml"
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Edit `~/.hermes-voice/config.toml` and set:

- the generated top-level gateway `token`;
- Telegram `api_id` and `api_hash`;
- `session_path = "/home/YOUR_USER/.hermes-voice/hermes.session"`;
- the allowlisted Hermes bot peer under `[chats.hermes]`.

Optional unlimited speech:

```bash
export HV_MAX_SPOKEN_CHARS=0
```

Use a positive value, such as `12000`, to retain a safety limit.

## 5. Authorize Telegram

```bash
uv run python -m hermes_voice.scripts.login
chmod 600 "$HOME/.hermes-voice/hermes.session"*
```

## 6. Run tests before installing the service

```bash
uv run python scripts/verify_readmes.py
uv run pytest -q
uv run ruff check .
uv run mypy --no-incremental hermes_voice
node --check hermes_voice/web/main.js
```

## 7. Test manually in the foreground

```bash
HV_MODE=telegram HV_SPEECH_BACKEND=auto \
uv run uvicorn hermes_voice.server.app:create_app \
  --factory --host 127.0.0.1 --port 8990
```

Wait for:

```bash
curl -fsS http://127.0.0.1:8990/healthz
```

Open `http://127.0.0.1:8990/`, enter the gateway token, press **Start**, select a topic, and complete the
manual checks in [REAL-MACHINE-TESTING.md](REAL-MACHINE-TESTING.md).

## 8. Install as a user systemd service

```bash
bash scripts/linux/install-systemd-user.sh
sudo loginctl enable-linger "$USER"
```

Check it:

```bash
systemctl --user status hermes-voice.service --no-pager
journalctl --user -u hermes-voice.service -n 100 --no-pager
curl -fsS http://127.0.0.1:8990/healthz
```

Preview the generated unit without changing the system:

```bash
bash scripts/linux/install-systemd-user.sh --dry-run
```

## 9. Install Tailscale and publish private HTTPS

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Configure or reuse a safe Serve route:

```bash
cd "$HOME/hermes-voice"
uv run python -m hermes_voice.scripts.configure_tailscale_serve
```

The command reports the private HTTPS URL. It does not replace an existing dashboard or other root route.
Use Serve, not Funnel.

## 10. Real-model automated check

Stop any service already using test port `8991`, then run:

```bash
uv run python scripts/run_real_machine_test.py --port 8991
```

This downloads/loads the real portable speech models, synthesizes a probe utterance, feeds it through VAD and
Faster-Whisper, receives parrot text and Kokoro audio over WebSocket, and writes a JSON report.

## Troubleshooting

```bash
ss -ltnp | grep ':8990' || true
systemctl --user status hermes-voice.service --no-pager
journalctl --user -u hermes-voice.service -n 200 --no-pager
tailscale serve status
```

First model warmup can take several minutes. Keep `config.toml` and all `.session` files out of Git.
