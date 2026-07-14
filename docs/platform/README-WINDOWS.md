
# Fresh install — Windows 10/11 x64

Native Windows is a candidate platform using Faster-Whisper and portable Kokoro. Do not call a Windows machine
fully supported until both the clean `windows-2025` workflow and the physical real-machine test pass.

## 1. Install prerequisites

Open PowerShell. Install Git, Node.js, FFmpeg, and uv using trusted installers or package managers. The official
uv installer is:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Open a new PowerShell window, then:

```powershell
uv python install 3.12
uv --version
```

Install Hermes Agent natively:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
```

Open a new terminal, then:

```powershell
hermes setup
hermes
hermes gateway setup
hermes gateway install
hermes gateway start
hermes gateway status
```

Enable private-chat topic mode through `@BotFather`, create a topic, and verify a same-topic reply.

## 2. Install Hermes Voice

```powershell
Set-Location $HOME
git clone https://github.com/Benalum/hermes-voice.git
Set-Location "$HOME\hermes-voice"
uv sync --locked --extra speech-portable --group dev
uv run python scripts/verify_platform.py --expected-backend portable
```

If dependency installation fails on Windows, do not work around it by deleting the lock file. Save the complete
error and treat native Windows as unsupported until the dependency markers or package versions are corrected.

## 3. Configure Telegram

```powershell
New-Item -ItemType Directory -Force "$HOME\.hermes-voice" | Out-Null
Copy-Item config.example.toml "$HOME\.hermes-voice\config.toml"
python -c "import secrets; print(secrets.token_urlsafe(32))"
notepad "$HOME\.hermes-voice\config.toml"
```

Use forward slashes in the TOML session path to avoid escaping problems:

```toml
session_path = "C:/Users/YOUR_USER/.hermes-voice/hermes.session"
```

Set the top-level gateway token, Telegram API credentials, and allowlisted bot peer. Authorize:

```powershell
uv run python -m hermes_voice.scripts.login
```

## 4. Validate and run

```powershell
uv run python scripts/verify_readmes.py
uv run pytest -q
uv run ruff check .
uv run mypy --no-incremental hermes_voice
node --check hermes_voice/web/main.js

$env:HV_MODE = "telegram"
$env:HV_SPEECH_BACKEND = "auto"
$env:HV_MAX_SPOKEN_CHARS = "0"
uv run uvicorn hermes_voice.server.app:create_app --factory --host 127.0.0.1 --port 8990
```

In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8990/healthz
```

Open `http://127.0.0.1:8990/` in Chrome or Edge and complete the manual checklist.

## 5. Start automatically at login

Preview the scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-hermes-voice-task.ps1 -DryRun
```

Install and start it:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-hermes-voice-task.ps1
```

Check or remove it:

```powershell
schtasks.exe /Query /TN "Hermes Voice" /V /FO LIST
powershell -ExecutionPolicy Bypass -File scripts\windows\install-hermes-voice-task.ps1 -Uninstall
```

## 6. Tailscale

Install the official Windows Tailscale application and sign in. Confirm `tailscale.exe` is available, then:

```powershell
uv run python -m hermes_voice.scripts.configure_tailscale_serve
```

If the CLI is not in `PATH`, the configurator checks the normal `%PROGRAMFILES%\Tailscale` location.

## 7. Real-model test

```powershell
uv run python scripts/run_real_machine_test.py --port 8991
```

The test validates actual portable TTS, VAD, Faster-Whisper, Uvicorn, and WebSocket flow. Browser microphone,
audible speaker output, Telegram, Tailscale HTTPS, and Task Scheduler restart still require manual confirmation.

## WSL2 fallback

When native speech dependency installation fails, install WSL2 with `wsl --install`, install Ubuntu, and follow the
Ubuntu guide inside WSL. Treat WSL2 as a separate deployment and document how Tailscale or Windows localhost reaches
its port before calling that setup production-ready.
