"""End-to-end verification against a LIVE gateway.

Streams a synthesized utterance into /ws exactly as the browser would and
asserts the full loop: transcript -> (relay) -> agent text -> spoken audio ->
back to listening.

    uv run python tests/e2e/verify.py [ws://127.0.0.1:8990/ws] [token]

Against a telegram-mode gateway this sends the transcribed phrase into the
active chat, so point the first configured chat at a test bot (or Saved
Messages) before running.
"""

from __future__ import annotations

import asyncio
import json
import sys

import numpy as np
import websockets

PHRASE = "ping"
FRAME_BYTES = 1024


async def synthesize_utterance() -> bytes:
    from hermes_voice.io.tts_kokoro import KokoroTts

    spoken24 = await KokoroTts().synthesize(PHRASE)
    audio24 = np.frombuffer(spoken24, dtype=np.int16).astype(np.float32)
    idx = np.arange(0, len(audio24), 1.5).astype(np.int64)
    return audio24[idx].astype(np.int16).tobytes()


async def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8990/ws"
    token = sys.argv[2] if len(sys.argv) > 2 else ""
    audio16 = await synthesize_utterance()

    saw: dict[str, object] = {}
    audio_frames = 0
    current_epoch: int | None = None

    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "token": token}))
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready", f"expected ready, got {ready}"
        print(f"✓ ready (chats: {[c['key'] for c in ready['chats']] or 'parrot'})")

        for i in range(0, len(audio16) - FRAME_BYTES, FRAME_BYTES):
            await ws.send(audio16[i : i + FRAME_BYTES])
        for _ in range(30):
            await ws.send(b"\x00" * FRAME_BYTES)

        deadline = asyncio.get_event_loop().time() + 240
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                print("✗ timed out waiting for the loop to complete")
                return 1
            msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
            if isinstance(msg, bytes):
                epoch = int.from_bytes(msg[:4], "little")
                if epoch == current_epoch:
                    audio_frames += 1
                continue
            control = json.loads(msg)
            kind = control["type"]
            saw[kind] = control
            if kind == "transcript":
                print(f"✓ transcript: {control['text']!r}")
            elif kind == "agent_text":
                print(f"✓ agent replied: {control['text'][:60]!r}")
            elif kind == "speak_start":
                current_epoch = control["epoch"]
            elif kind == "state" and control["name"] == "listening" and "transcript" in saw:
                break

    ok = True
    for required in ("transcript", "agent_text", "speak_start"):
        if required not in saw:
            print(f"✗ never saw {required}")
            ok = False
    if audio_frames < 1:
        print("✗ no spoken audio frames received")
        ok = False
    if ok:
        print(f"✓ spoken audio: {audio_frames} frame(s); session back to listening")
        print("PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
