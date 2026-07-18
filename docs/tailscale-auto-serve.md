# Automatic Tailscale Serve for Hermes Voice

Hermes Voice continues listening only on:

```text
http://127.0.0.1:8990
```

Tailscale Serve provides the private HTTPS edge for devices in the same
tailnet.

## Conflict-safe behavior

The configurator reads the existing Serve configuration using:

```text
tailscale serve status --json
```

It then behaves as follows:

1. If a root Serve route already proxies to Hermes Voice, it reports every
   matching URL and changes nothing.
2. If no matching route exists and HTTPS port 443 is free, it creates a
   persistent background route on port 443.
3. If the requested port is already used by another service, it refuses to
   replace that route.
4. Replacement requires both an explicit `--https-port` and `--force`.

This prevents Hermes Voice from accidentally replacing a dashboard or another
application on the same Tailscale node.

## Configure or verify

```text
uv run python -m hermes_voice.scripts.configure_tailscale_serve
```

Running the command repeatedly is safe. Existing matching routes are reused.

## Preview

The dry run still reads the current Serve configuration, but it does not make
changes:

```text
uv run python -m hermes_voice.scripts.configure_tailscale_serve --dry-run
```

## Select another port

```text
uv run python -m hermes_voice.scripts.configure_tailscale_serve --https-port 9443
```

## Disable a specific listener

An explicit port is required:

```text
uv run python -m hermes_voice.scripts.configure_tailscale_serve --disable --https-port 9443
```

The configurator never runs `tailscale serve reset`, because reset could remove
unrelated routes.

## Operating systems

### Linux

Ensure `tailscaled.service` is enabled and running. Tailscale background Serve
configuration persists independently of the Hermes Voice systemd service.

### macOS

The configurator supports a Tailscale CLI in `PATH` and the usual application
bundle CLI locations. GUI variants typically start after user login. A
CLI-only `tailscaled` installation can run before login.

### Windows

The configurator detects `tailscale.exe`, but native Windows speech deployment
is not currently documented as a supported Hermes Voice target.

## Security

- Uses Tailscale Serve, not Funnel.
- Hermes Voice remains bound to loopback.
- Access remains limited by tailnet policy.
- The Hermes Voice gateway token is still required.
