
"""End-to-end verification against a live Hermes Voice gateway."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import numpy as np
import websockets

PHRASE = "Hermes voice platform test"
FRAME_BYTES = 1024


async def synthesize_utterance() -> bytes:
    from hermes_voice.io.speech_factory import detect_speech_backend

    if detect_speech_backend() == "mlx":
        from hermes_voice.io.tts_kokoro import KokoroTts

        tts = KokoroTts()
    else:
        from hermes_voice.io.tts_kokoro_portable import PortableKokoroTts

        tts = PortableKokoroTts()

    spoken24 = await tts.synthesize(PHRASE)
    audio24 = np.frombuffer(spoken24, dtype=np.int16)
    indices = np.arange(0, len(audio24), 1.5).astype(np.int64)
    return audio24[indices].astype(np.int16).tobytes()


async def run(args: argparse.Namespace) -> int:
    audio16 = args.pcm_file.read_bytes() if args.pcm_file else await synthesize_utterance()
    saw: dict[str, object] = {}
    audio_frames = 0
    current_epoch: int | None = None

    async with websockets.connect(args.url, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "token": args.token}))
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready", f"expected ready, got {ready}"
        print("PASS ready")

        for offset in range(0, len(audio16), FRAME_BYTES):
            await ws.send(audio16[offset : offset + FRAME_BYTES])
        for _ in range(30):
            await ws.send(b"\x00" * FRAME_BYTES)

        deadline = asyncio.get_running_loop().time() + args.timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                print("FAIL timed out")
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
                print(f"PASS transcript: {control['text']!r}")
            elif kind == "agent_text":
                print(f"PASS agent text: {control['text'][:80]!r}")
            elif kind == "speak_start":
                current_epoch = control["epoch"]
            elif kind == "state" and control["name"] == "listening" and "transcript" in saw:
                break

    missing = [kind for kind in ("transcript", "agent_text", "speak_start") if kind not in saw]
    if missing or audio_frames < 1:
        print(f"FAIL missing={missing} audio_frames={audio_frames}")
        return 1
    print(f"PASS spoken audio frames={audio_frames}; returned to listening")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="ws://127.0.0.1:8990/ws")
    parser.add_argument("token", nargs="?", default="")
    parser.add_argument("--pcm-file", type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
