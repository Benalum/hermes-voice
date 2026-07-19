# Portable Hermes container stack

This deployment runs two isolated Hermes agents while keeping all expensive
STT, TTS, and VAD models in one shared `hermes-speech` service.

| Service | Purpose | Persistent data |
|---|---|---|
| `hermes1-agent` | Official Hermes Agent gateway | `state/hermes1-agent` |
| `hermes1-voice` | Browser microphone, speaker, and Telegram relay | `state/hermes1-voice` |
| `tailscale-hermes1` | Optional private HTTPS identity | Docker volume |
| `hermes2-agent` | Independent official Hermes Agent gateway | `state/hermes2-agent` |
| `hermes2-voice` | Independent browser voice gateway | `state/hermes2-voice` |
| `tailscale-hermes2` | Optional private HTTPS identity | Docker volume |

The two agents never share Hermes state, Telegram bot tokens, Telethon user
sessions, browser tokens, or speech client tokens. The shared speech service is
private infrastructure and is not exposed through Tailscale Serve or Funnel.

## Requirements

- Docker Engine with Compose v2, or Docker Desktop.
- A reachable `hermes-speech` v1 endpoint.
- Separate `hermes1` and `hermes2` client tokens from that endpoint.
- Two Telegram bots for the Hermes Agent gateways.
- One authorized Telegram user account for each Hermes Voice relay session.
- Optional reusable, pre-authorized Tailscale auth keys for the two sidecars.

Linux runs the containers natively. Docker Desktop supplies the Linux VM on
macOS and Windows. The image is built from Python's multi-architecture base and
contains no platform-specific speech models, making both AMD64 and ARM64
practical targets.

## 1. Create local configuration

Run from the repository root:

```bash
cp deploy/compose/.env.example .env
mkdir -p \
  deploy/compose/state/hermes1-agent \
  deploy/compose/state/hermes1-voice \
  deploy/compose/state/hermes2-agent \
  deploy/compose/state/hermes2-voice

cp deploy/compose/templates/hermes1-voice-config.toml \
  deploy/compose/state/hermes1-voice/config.toml
cp deploy/compose/templates/hermes2-voice-config.toml \
  deploy/compose/state/hermes2-voice/config.toml

chmod 600 \
  .env \
  deploy/compose/state/hermes1-voice/config.toml \
  deploy/compose/state/hermes2-voice/config.toml
```

Edit `.env` with the matching shared-speech URL, client ID, and token for each
agent. Compose passes each credential only to the matching Hermes Agent and
Hermes Voice pair. Generate different browser tokens for the two
voice configuration files:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Fill in the Telegram API ID, API hash, bot peer, and generated browser token in
each voice `config.toml`. Never commit anything under `deploy/compose/state`.

On native Linux, ensure UID 10001 can write the two `*-voice` state
directories. Docker Desktop normally handles bind-mounted ownership itself:

```bash
sudo chown -R 10001:10001 \
  deploy/compose/state/hermes1-voice \
  deploy/compose/state/hermes2-voice
```

## 2. Configure both official Hermes Agent containers

The stack uses Nous Research's official `nousresearch/hermes-agent` image and
its `/opt/data` persistence contract. Run the account/model setup independently:

```bash
docker compose run --rm hermes1-agent setup
docker compose run --rm hermes2-agent setup
```

Configure their Telegram bots and allowed numeric Telegram user IDs during
setup. Never point both containers at the same state directory.

Install the shared-speech command providers into each persisted configuration:

```bash
bash deploy/compose/configure-agent.sh hermes1
bash deploy/compose/configure-agent.sh hermes2
```

The mounted bridge gives Telegram voice notes and `/voice on` the same shared
STT and TTS service used by the browser gateway.

## 3. Authorize both Hermes Voice relay sessions

Hermes Voice uses an authorized Telegram user session to speak with its one
configured Hermes bot. It does not start a second Bot API poller with the bot's
token.

```bash
docker compose run --rm hermes1-voice python -m hermes_voice.scripts.login
docker compose run --rm hermes2-voice python -m hermes_voice.scripts.login
```

Use separate session files and confirm the target bot in each `config.toml`.

## 4. Start and verify the private local endpoints

```bash
docker compose up -d --build \
  hermes1-agent hermes1-voice \
  hermes2-agent hermes2-voice

curl -fsS http://127.0.0.1:8991/healthz
curl -fsS http://127.0.0.1:8992/healthz
docker compose ps
```

Hermes Voice binds `0.0.0.0:8990` only inside its container so the optional
Tailscale sidecar can reach it. Compose publishes each port exclusively on the
host's loopback address.

## 5. Add private Tailscale HTTPS

Create two different reusable, pre-authorized Tailscale keys with the minimum
tags permitted by your tailnet policy. Store them only in `.env`, then start
the optional profile:

```bash
docker compose --profile tailscale up -d
docker compose logs --tail 50 tailscale-hermes1 tailscale-hermes2
```

The sidecars use userspace networking, persistent identity volumes, and Serve
configuration that explicitly disables Funnel. Expected MagicDNS names are:

```text
https://hermes1-voice.<tailnet>.ts.net/
https://hermes2-voice.<tailnet>.ts.net/
```

Apply tailnet ACL grants so only the intended users/devices can reach these
nodes on TCP 443. The Hermes Voice browser token remains required after the
Tailscale identity check.

## Updating and recovery

```bash
docker compose pull
docker compose build --pull hermes1-voice hermes2-voice
docker compose up -d
docker compose logs --tail 100
```

Back up `deploy/compose/state` and the two named Tailscale volumes. Do not back
up one agent's state over the other. The official Hermes Agent image is
stateless; its memories, sessions, configuration, and gateway state live under
the corresponding bind mount.

## Security boundaries

- Never use Tailscale Funnel for this stack.
- Keep `hermes-speech` on a private network and firewall it to known clients.
- Use different speech tokens, browser tokens, Telegram bots, and state paths.
- Restrict every Telegram bot to numeric allowed-user IDs.
- Do not publish the Hermes Agent dashboard or API unless authentication is
  configured and the exposure is intentional.
- Do not mount the Docker socket into either Hermes Agent by default.
