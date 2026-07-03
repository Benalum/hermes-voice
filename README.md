# hermes-voice

Realtime voice conversations with your Hermes agents on Telegram. Speak from a
browser on any device; a gateway on the Mac Studio does everything locally:

```
browser mic ──WS──▶ silero VAD ─▶ parakeet STT ─▶ Telegram (as you, via Telethon)
browser spk ◀─WS── Kokoro TTS ◀─ reply settling ◀─ agent's reply in the chat
```

History stays 100% in Telegram - the gateway just types what you say into the
chosen chat and reads the agent's answer back. Agents need zero changes and can
run anywhere. Barge-in supported: speak over the voice to interrupt it.

## Setup (once)

1. **Install** (Python 3.12 via [uv](https://docs.astral.sh/uv/)):

   ```sh
   uv sync --extra speech
   ```

2. **Configure.** Get `api_id`/`api_hash` at <https://my.telegram.org/apps>, then:

   ```sh
   mkdir -m 700 -p ~/.hermes-voice
   cp config.example.toml ~/.hermes-voice/config.toml
   chmod 600 ~/.hermes-voice/config.toml
   $EDITOR ~/.hermes-voice/config.toml   # api creds, token, one [chats.*] per agent
   ```

3. **Log in to Telegram** (interactive: phone code + optional 2FA):

   ```sh
   uv run python -m hermes_voice.scripts.login
   ```

4. **Expose over Tailscale** (HTTPS is required for browser mic access):

   ```sh
   tailscale serve --bg https / http://127.0.0.1:8990
   ```

5. **Run as a service:**

   ```sh
   mkdir -p ~/Library/Logs/hermes-voice
   cp launchd/com.stephen.hermes-voice.plist ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.stephen.hermes-voice.plist
   ```

   First start loads + warms all three models; `curl localhost:8990/healthz`
   shows `{"models": "warm", "telegram": "connected"}` when ready.

Open `https://<mac-studio>.<tailnet>.ts.net/` from the laptop or phone, enter
the token from your config when prompted, pick a chat, press Start, talk.

## Dev modes

```sh
HV_MODE=parrot uv run uvicorn hermes_voice.server.app:create_app --factory --port 8990
```

- `telegram` (default): the real thing
- `parrot`: local loop, speaks your words back - no Telegram needed
- `echo`: raw PCM echo, transport debugging

## Tests

```sh
uv run pytest                  # pure + wiring tests (fast, no models/network)
uv run pytest -m models        # real MLX model checks (downloads on first run)
uv run pytest -m telegram      # live checks against your logged-in session
uv run python tests/e2e/verify.py   # full loop against a running gateway
uv run mypy && uv run ruff check .
```

## Layout

- `hermes_voice/kit/` - pure, fully-tested logic: WS protocol, turn detection
  (VAD probabilities → speech start/end/barge-in), session state machine,
  reply settling (multi-message / edit-streaming / typing-hold), text
  normalization and sentence chunking for TTS
- `hermes_voice/io/` - adapters: silero-vad, parakeet-mlx, Kokoro (mlx-audio),
  Telethon relay
- `hermes_voice/server/` - FastAPI shell, orchestrator (interprets the pure
  machine's effects), config
- `hermes_voice/web/` - vanilla-JS client with mic/player AudioWorklets

## Notes

- The Telethon session file (`~/.hermes-voice/*.session`) can read and send as
  your entire Telegram account. It stays chmod 600, the server binds
  127.0.0.1 (tailnet-only via `tailscale serve`; never use `funnel`), and the
  gateway can only send to chats allowlisted in the config.
- Messages an agent edits *after* they've been spoken are not re-spoken (v1).
- `mlx-audio <= 0.4.4` has a Kokoro vocoder length bug; a contained patch in
  `hermes_voice/io/tts_kokoro.py` works around it.
