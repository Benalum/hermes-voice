
# Hermes Voice

Hermes Voice is a private browser-based voice gateway for Hermes Agent conversations on Telegram.
The browser captures and plays audio; the host running Hermes Voice performs VAD, speech-to-text,
Telegram relay, and text-to-speech locally.

```text
browser microphone
→ WebSocket
→ Silero VAD
→ platform speech-to-text
→ Telegram topic
→ Hermes Agent
→ Telegram reply
→ platform text-to-speech
→ WebSocket
→ browser speaker
```

## Platform support

Support status reflects the strongest validation completed for each platform.

| Platform | Installation and tests | Real speech-model CI | Physical-machine validation | Status |
|---|---|---|---|---|
| Ubuntu 24.04 x64 | Passed | Passed | Confirmed | Supported |
| Windows 10/11 x64 | Passed | Passed | Pending | CI validated |
| macOS 15 Apple Silicon | Passed | Passed | Pending | CI validated |
| macOS 15 Intel | Passed | Under investigation | Pending | Experimental |

### Validation terminology

- **Supported:** Automated validation passed and the application was exercised on physical hardware.
- **CI validated:** Installation, tests, and real-model checks passed on GitHub-hosted runners, but complete physical-machine testing is still pending.
- **Experimental:** Installation and automated tests may pass, but one or more important runtime paths remain unresolved.

GitHub-hosted validation does not replace testing with a physical microphone, speakers, browser permissions, Telegram, Tailscale, operating-system service management, and startup after reboot.

See [the detailed platform validation record](docs/platform/VALIDATION-STATUS.md).

## Platform guides

Use the guide matching the machine that will run the Hermes Voice gateway:

- [Ubuntu 24.04 / Linux](docs/platform/README-UBUNTU-LINUX.md)
- [macOS on Apple Silicon](docs/platform/README-MACOS-APPLE-SILICON.md)
- [macOS on Intel](docs/platform/README-MACOS-INTEL.md)
- [Windows 10/11 x64](docs/platform/README-WINDOWS.md)
- [Platform support and test status](docs/platform/README.md)

Do not combine commands from different platform guides.

## Speech backend selection

| Host | Backend selected by `HV_SPEECH_BACKEND=auto` |
|---|---|
| macOS Apple Silicon | Parakeet MLX STT + Kokoro MLX TTS |
| Ubuntu/Linux x64 | Faster-Whisper STT + portable Kokoro TTS |
| macOS Intel | Faster-Whisper STT + portable Kokoro TTS |
| Windows x64 | Faster-Whisper STT + portable Kokoro TTS |

## Fast development check

Install Python 3.12 and dependencies using `uv`, then run the model-free suite:

```bash
uv sync --locked --extra speech --group dev
uv run pytest -q
uv run ruff check .
uv run mypy --no-incremental hermes_voice
node --check hermes_voice/web/main.js
```

Start a local, credential-free parrot session:

```bash
HV_MODE=parrot uv run uvicorn hermes_voice.server.app:create_app \
  --factory --host 127.0.0.1 --port 8990
```

On PowerShell:

```powershell
$env:HV_MODE = "parrot"
uv run uvicorn hermes_voice.server.app:create_app --factory --host 127.0.0.1 --port 8990
```

Open `http://127.0.0.1:8990/` and press **Start**.

## Speaker filtering and command mute

Hermes Voice can optionally reject utterances that do not match an enrolled
speaker before speech-to-text runs. It also supports synchronized browser and
spoken command mute controls. Say **“Hermes mute me”** to suppress ordinary
transcripts at the server, then **“Hermes unmute me”** to resume forwarding.

Command mute deliberately keeps the browser microphone stream connected so the
server can recognize an unmute command locally. Muted speech is not relayed to
Telegram or the agent, and neither a spoken mute command nor later muted speech
interrupts reply playback. Use the
operating system or browser microphone control when no audio may leave the
device at all.

See [Speaker filtering and voice mute](docs/speaker-filtering-and-voice-mute.md)
for installation, enrollment, calibration, privacy behavior, and troubleshooting.

## Automated platform verification

The repository includes:

- `.github/workflows/platform-clean-install.yml` for clean GitHub-hosted runners;
- `scripts/verify_platform.py` for dependency/backend/static validation;
- `scripts/run_real_machine_test.py` for real-model loop testing on actual hardware;
- `scripts/verify_readmes.py` to prevent documentation drift.

Run the local platform probe:

```bash
uv run python scripts/verify_platform.py
```

Run the real-model test on a physical machine after the speech models have permission to download:

```bash
uv run python scripts/run_real_machine_test.py
```

The real-model test validates the platform backend, VAD, STT, TTS, Uvicorn, WebSocket protocol,
and return to the listening state. A final browser microphone/speaker checklist remains manual because
CI cannot prove physical hardware permissions or audible output.

## Private browser hosting with Tailscale

Keep Hermes Voice bound to `127.0.0.1:8990`. Configure or verify a private HTTPS route with:

```bash
uv run python -m hermes_voice.scripts.configure_tailscale_serve
```

The configurator reuses an existing matching route and refuses to replace another service unless
replacement is explicitly requested. It uses Tailscale Serve, never Funnel.

## Security

- Never commit `~/.hermes-voice/config.toml` or Telegram `.session` files.
- Keep the gateway bound to loopback.
- Use Tailscale Serve or an SSH tunnel for remote browser access.
- Treat the Hermes Voice gateway token, Telegram API hash, BotFather token, and Telethon session as secrets.
- Treat speaker enrollment WAVs and `speakers.json` as sensitive voice data; never commit them.
- `HV_MAX_SPOKEN_CHARS=0` disables character truncation; use a positive limit when unbounded speech is undesirable.
