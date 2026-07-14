
# Fresh install — macOS Apple Silicon

Supported architecture: `arm64`. This path uses Parakeet MLX and Kokoro MLX.

## 1. Confirm architecture and install prerequisites

```bash
uname -m
```

Expected: `arm64`.

Install Apple Command Line Tools, Homebrew packages, `uv`, and Python 3.12:

```bash
xcode-select --install
brew install ffmpeg git node uv
uv python install 3.12
```

The official uv installer is an alternative:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env" 2>/dev/null || true
```

## 2. Install Hermes Agent

Use the Hermes Desktop installer, or the CLI installer:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source "$HOME/.zshrc"
hermes setup
hermes
```

Configure and verify Telegram:

```bash
hermes gateway setup
hermes gateway install
hermes gateway start
hermes gateway status
```

Enable private-chat topics through `@BotFather`, create a topic, and verify a same-topic reply.

## 3. Install Hermes Voice

```bash
cd "$HOME"
git clone https://github.com/Benalum/hermes-voice.git
cd "$HOME/hermes-voice"
uv sync --locked --extra speech --group dev
uv run python scripts/verify_platform.py --expected-backend mlx
```

Do not force the portable backend on Apple Silicon unless diagnosing an MLX issue.

## 4. Configure and authorize Telegram

```bash
mkdir -p "$HOME/.hermes-voice"
chmod 700 "$HOME/.hermes-voice"
cp config.example.toml "$HOME/.hermes-voice/config.toml"
chmod 600 "$HOME/.hermes-voice/config.toml"
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Set the generated top-level token, Telegram API credentials, bot peer, and:

```toml
session_path = "/Users/YOUR_USER/.hermes-voice/hermes.session"
```

Authorize:

```bash
uv run python -m hermes_voice.scripts.login
chmod 600 "$HOME/.hermes-voice/hermes.session"*
```

## 5. Validate and test in the foreground

```bash
uv run python scripts/verify_readmes.py
uv run pytest -q
uv run ruff check .
uv run mypy --no-incremental hermes_voice
node --check hermes_voice/web/main.js

HV_MODE=telegram HV_SPEECH_BACKEND=auto \
uv run uvicorn hermes_voice.server.app:create_app \
  --factory --host 127.0.0.1 --port 8990
```

Check `http://127.0.0.1:8990/healthz`, then complete the browser checks in
[REAL-MACHINE-TESTING.md](REAL-MACHINE-TESTING.md). macOS may request microphone and local-network permissions.

## 6. Install a launch agent

```bash
zsh scripts/macos/install-launch-agent.sh
```

Preview without changing launchd:

```bash
zsh scripts/macos/install-launch-agent.sh --dry-run
```

Check logs:

```bash
tail -n 100 "$HOME/Library/Logs/hermes-voice/stdout.log"
tail -n 100 "$HOME/Library/Logs/hermes-voice/stderr.log"
launchctl print "gui/$(id -u)/com.hermes.voice"
```

## 7. Tailscale Serve

Install the recommended Standalone Tailscale application, sign in, and enable CLI integration in the app.
Then run:

```bash
cd "$HOME/hermes-voice"
uv run python -m hermes_voice.scripts.configure_tailscale_serve
```

The GUI Tailscale variants normally become available after user login. The Serve configuration persists after
Tailscale restarts when created with `--bg`.

## 8. Real-model test

```bash
uv run python scripts/run_real_machine_test.py --port 8991
```

A passing report proves the MLX VAD/STT/TTS/server/WebSocket loop on that Mac. Physical microphone and speaker
confirmation remains a manual acceptance step.
