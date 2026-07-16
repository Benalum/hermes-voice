# Hermes Voice Platform Validation Status

Last updated: July 16, 2026

## Validation levels

- **Supported:** Automated validation passed and the application was exercised on physical hardware.
- **CI validated:** Clean installation, tests, and real-model checks passed on GitHub-hosted runners. Physical-machine testing remains pending.
- **Experimental:** Installation or tests may pass, but an important runtime path remains incomplete or under investigation.

## Current status

| Platform | Clean install | Unit tests | Real models | Physical hardware | Status |
|---|---:|---:|---:|---:|---|
| Ubuntu 24.04 x64 | Pass | Pass | Pass | Pass | Supported |
| Windows 10/11 x64 | Pass | Pass | Pass | Pending | CI validated |
| macOS 15 Apple Silicon | Pass | Pass | Pass | Pending | CI validated |
| macOS 15 Intel | Pass | Pass | Incomplete | Pending | Experimental |

## Latest validation candidate

- Branch: `feature/platform-validation`
- Commit: `3cbbe27`
- Python: 3.12
- Local suite: 188 passed, 6 deselected
- Clean-install workflow: passed on Ubuntu, Windows, Apple Silicon macOS, and Intel macOS
- Real-model workflow: passed on Ubuntu, Windows, and Apple Silicon macOS
- Intel macOS real-model result: incomplete; the automated speech loop failed or timed out during model execution

## Intel macOS status

Intel macOS dependency installation, backend selection, documentation
validation, unit tests, Ruff, Mypy, JavaScript syntax checks, and LaunchAgent
rendering pass in CI.

The Intel portable real-model path remains experimental until the complete
speech loop passes consistently and is confirmed on a physical Intel Mac.

The current implementation includes:

- a dedicated Faster-Whisper subprocess;
- an Intel-specific CTranslate2 compatibility version;
- bounded single-threaded CTranslate2 inference;
- explicit runtime-version validation.

Apple Silicon is the recommended macOS platform.

## Physical-machine checks

CI does not validate all hardware and operating-system behavior. Each physical
installation should confirm:

1. Microphone permission and capture
2. Speech transcription
3. Telegram round trip
4. Speech synthesis and browser playback
5. Stop Speech and barge-in
6. Tailscale HTTPS access
7. Startup after reboot or login
8. Extended operation without worker stalls or resource leaks
