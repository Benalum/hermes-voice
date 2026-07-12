# Hermes Voice platform setup guides

> **Status: rough guides.** These instructions are intended to get a new installation from zero to a working Hermes Voice setup, but they will probably need refinement for each operating system, hardware configuration, browser, Telegram account, and Hermes Agent release. Do not treat them as finished production documentation yet.

## Current platform targets

| Guide | Speech backend selected by `uv sync --extra speech` |
|---|---|
| [Ubuntu / Linux](README-UBUNTU-LINUX.md) | Faster-Whisper STT + portable Kokoro TTS |
| [macOS — Apple Silicon](README-MACOS-APPLE-SILICON.md) | Parakeet MLX STT + Kokoro MLX TTS |
| [macOS — Intel](README-MACOS-INTEL.md) | Faster-Whisper STT + portable Kokoro TTS |

These are the three platform targets currently represented by the project. Native Windows is not yet documented as a supported Hermes Voice speech target.

## Current architecture

```text
Browser microphone
→ local VAD and speech-to-text
→ selected Telegram topic
→ Hermes Agent Telegram bot
→ reply in the same Telegram topic
→ local text-to-speech
→ browser audio
```

Telegram is the authoritative store for topic names and message history. Hermes Voice fetches topic history when needed and keeps the active view in memory. It does not create its own chat-history database.

## Shared assumptions

Before using any guide:

1. Hermes Agent must respond successfully in a normal terminal chat.
2. The Hermes Agent Telegram gateway must be configured and running.
3. The Telegram bot must have Threaded Mode enabled.
4. At least one Telegram topic must exist in the private bot chat.
5. The Hermes Voice machine must be able to reach Telegram and download speech models on first use.
6. Keep all Telegram tokens, API credentials, browser tokens, and `.session` files out of Git.

## Required Telegram and browser credentials

Hermes Voice uses three different credentials. They are not interchangeable:

| Credential | Where it comes from | Where it is used |
|---|---|---|
| BotFather bot token | `@BotFather` after creating the Hermes bot | Entered during `hermes gateway setup`; it belongs to Hermes Agent, not the Hermes Voice TOML file |
| Telegram `api_id` and `api_hash` | `https://my.telegram.org/apps` | Stored under `[telegram]` in `~/.hermes-voice/config.toml` |
| Hermes Voice gateway token | Generated locally with `secrets.token_urlsafe(32)` | Stored as the top-level `token` in `~/.hermes-voice/config.toml`; entered in each browser/device that connects |

The private Hermes bot chat must also have topics enabled:

```text
@BotFather
→ select the bot
→ Bot Settings
→ Thread Settings
→ enable Threaded Mode
```

Telegram may change the exact menu wording. The required result is that the bot has private-chat topic/thread mode enabled and the user is allowed to create topics.

To display the current Hermes Voice gateway token later:

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

Treat the printed value like a password.

## Use Hermes Voice from another device with Tailscale

Keep Hermes Voice bound to `127.0.0.1:8990`, then publish it privately to the tailnet with Tailscale Serve:

```bash
tailscale serve --bg 8990
tailscale serve status
```

On Linux, the command may require `sudo`.

Tailscale prints a private HTTPS URL similar to:

```text
https://hermes.example-tailnet.ts.net
```

Install Tailscale on the phone, tablet, or second computer, join the same tailnet, open that HTTPS address, and enter the Hermes Voice gateway token when prompted. HTTPS is important for browser microphone permission and secure WebSockets.

Use **Tailscale Serve**, not **Tailscale Funnel**, unless public Internet exposure is intentionally desired.

## Repository status

Until the Telegram topic work is merged into the default branch, use:

```bash
git clone \
  --branch feature/telegram-chat-topics \
  https://github.com/Benalum/hermes-voice.git
```

After the feature is merged, replace the branch name with the stable release branch or tag.
