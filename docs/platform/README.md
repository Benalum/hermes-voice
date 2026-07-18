
# Hermes Voice platform support and validation

This directory contains fresh-install guides for the operating system running the Hermes Voice gateway.

## Current support matrix

| Platform | Speech backend | Automated result | Physical-machine result | Status |
|---|---|---|---|---|
| Ubuntu 24.04 x64 | Portable | Clean install and real-model CI passed | Confirmed on the Hermes Ubuntu host | Supported |
| macOS 15 Apple Silicon | MLX | Clean install and real-model CI passed | Pending | CI validated |
| macOS 15 Intel | Portable | Clean install passed; real-model reliability remains under investigation | Pending | Experimental |
| Windows 10/11 x64 | Portable | Clean install and real-model CI passed | Pending | CI validated |

A green GitHub Actions job proves that a new hosted virtual machine can
install the locked dependency set, select the correct backend, import the
platform adapters, and complete the automated checks.

It does not prove microphone permission, audible speaker output, Telegram
credentials, Tailscale login, operating-system startup behavior, or model
performance on a particular physical computer.

See [VALIDATION-STATUS.md](VALIDATION-STATUS.md) for the dated validation
record.
## Guides

- [Ubuntu 24.04 / Linux](README-UBUNTU-LINUX.md)
- [macOS Apple Silicon](README-MACOS-APPLE-SILICON.md)
- [macOS Intel](README-MACOS-INTEL.md)
- [Windows x64](README-WINDOWS.md)
- [Real-machine validation](REAL-MACHINE-TESTING.md)

## Automated validation

The workflow uses pinned operating-system labels rather than moving `-latest` aliases:

```text
ubuntu-24.04
macos-15
macos-15-intel
windows-2025
```

Run the same checks locally:

```bash
uv sync --locked --extra speech --group dev
uv run python scripts/verify_readmes.py
uv run python scripts/verify_platform.py
uv run pytest -q
uv run ruff check .
uv run mypy --no-incremental hermes_voice
node --check hermes_voice/web/main.js
```

## Real-machine acceptance rule

A platform is only marked fully verified after all of the following pass on physical hardware:

1. Fresh clone and locked dependency installation.
2. Platform probe.
3. Actual model warmup and real-model loop test.
4. Telegram login and topic round trip.
5. Browser microphone permission and transcription.
6. Audible complete playback through the browser.
7. Stop Speech and intentional barge-in followed by a complete later reply.
8. Persistent restart through systemd, launchd, or Task Scheduler.
9. Private HTTPS access through Tailscale Serve.

## Official references used by these guides

- uv installation: https://docs.astral.sh/uv/getting-started/installation/
- uv GitHub Actions: https://docs.astral.sh/uv/guides/integration/github/
- GitHub runner images: https://github.com/actions/runner-images
- Hermes Agent installation: https://hermes-agent.nousresearch.com/docs/getting-started/installation
- Tailscale Serve: https://tailscale.com/docs/reference/tailscale-cli/serve
