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

## Repository status

Until the Telegram topic work is merged into the default branch, use:

```bash
git clone \
  --branch feature/telegram-chat-topics \
  https://github.com/Benalum/hermes-voice.git
```

After the feature is merged, replace the branch name with the stable release branch or tag.
