
# Real-machine validation

Run this process on each physical operating system before marking it fully supported.

## Automated real-model loop

From a clean clone with dependencies installed:

```bash
uv run python scripts/run_real_machine_test.py --port 8991
```

PowerShell uses the same command.

The script:

1. records OS, architecture, Python, and selected backend;
2. synthesizes a spoken probe using the platform TTS model;
3. starts a credential-free parrot gateway with real VAD/STT/TTS models;
4. feeds the probe through the WebSocket exactly as a browser sends PCM;
5. requires transcript, agent text, audio frames, and return to listening;
6. verifies `/`, `/static/main.js`, and `/healthz`;
7. writes a JSON evidence report under `reports/real-machine/`.

This is a real model and server test, but it cannot prove physical microphone permission or audible speaker output.

## Manual browser acceptance

Start the real Telegram service, connect through the intended browser URL, and record pass/fail for:

- Gateway token accepted.
- Correct Telegram chats/topics listed.
- Microphone permission granted.
- Spoken question is transcribed correctly.
- Message reaches the selected Telegram topic.
- Hermes reply appears in the same topic.
- At least 20 sentences play completely.
- No `message truncated, see Telegram` unless a positive limit was intentionally configured.
- Stop Speech halts promptly.
- The next reply after Stop Speech plays completely.
- Intentional barge-in halts the old reply.
- The next reply after barge-in plays completely.
- Browser hard refresh and reconnect work.
- Tailscale HTTPS works from a second tailnet device.
- Service restarts after reboot/login.

## Evidence to save

Save the JSON report, platform version, architecture, service status, Tailscale Serve status, and relevant logs.
Never include gateway tokens, Telegram API hashes, BotFather tokens, or `.session` contents.
