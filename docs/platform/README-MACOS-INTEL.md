
# Fresh install — macOS Intel

Supported architecture: `x86_64`. This path uses Faster-Whisper and portable Kokoro, not MLX.

## 1. Confirm architecture and install prerequisites

```bash
uname -m
```

Expected: `x86_64`.

```bash
xcode-select --install
brew install ffmpeg git node uv
uv python install 3.12
```

## 2. Install Hermes Agent and Telegram gateway

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source "$HOME/.zshrc"
hermes setup
hermes
hermes gateway setup
hermes gateway install
hermes gateway start
hermes gateway status
```

Enable BotFather private-chat topic mode, create a topic, and verify a reply.

## 3. Install Hermes Voice

```bash
cd "$HOME"
git clone https://github.com/Benalum/hermes-voice.git
cd "$HOME/hermes-voice"
uv sync --locked --extra speech --group dev
uv run python scripts/verify_platform.py --expected-backend portable
```

Do not set `HV_SPEECH_BACKEND=mlx` on an Intel Mac.

Intel macOS uses a compatibility set of `numpy==1.26.4`, `torch==2.2.2`, `torchaudio==2.2.2`, `transformers==4.57.6`, `onnxruntime==1.23.2`, `numba==0.60.0`, and `llvmlite==0.43.0`. These versions provide compatible Python 3.12 x86_64 macOS wheels and preserve support for the portable Kokoro speech stack. Do not remove these Intel-specific pins or bypass the lock file.

## 4. Configure and authorize Telegram

```bash
mkdir -p "$HOME/.hermes-voice"
chmod 700 "$HOME/.hermes-voice"
cp config.example.toml "$HOME/.hermes-voice/config.toml"
chmod 600 "$HOME/.hermes-voice/config.toml"
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Set the top-level token, API credentials, peer, and an absolute macOS session path. Then:

```bash
uv run python -m hermes_voice.scripts.login
chmod 600 "$HOME/.hermes-voice/hermes.session"*
```

## 5. Validate and run

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

## 6. launchd and Tailscale

Install the launch agent and the recommended Standalone Tailscale application:

```bash
zsh scripts/macos/install-launch-agent.sh
```

Enable Tailscale CLI integration, then run:

```bash
uv run python -m hermes_voice.scripts.configure_tailscale_serve
```

## 7. Real-model test

```bash
uv run python scripts/run_real_machine_test.py --port 8991
```

Intel speech may be significantly slower than Apple Silicon or a modern Linux system. The test report records
startup and loop duration; evaluate whether the hardware is fast enough for interactive use.
