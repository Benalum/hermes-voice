
#!/usr/bin/env python3
"""Generate 16 kHz mono int16 PCM using the current platform TTS backend."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import numpy as np

from hermes_voice.kit.ports import TtsPort


async def synthesize(text: str) -> bytes:
    from hermes_voice.io.speech_factory import detect_speech_backend

    tts: TtsPort
    if detect_speech_backend() == "mlx":
        from hermes_voice.io.tts_kokoro import KokoroTts

        tts = KokoroTts()
    else:
        from hermes_voice.io.tts_kokoro_portable import PortableKokoroTts

        tts = PortableKokoroTts()

    pcm24 = await tts.synthesize(text)
    samples24 = np.frombuffer(pcm24, dtype=np.int16)
    indices = np.arange(0, len(samples24), 1.5).astype(np.int64)
    return samples24[indices].astype(np.int16).tobytes()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--text", default="Hermes voice platform test")
    args = parser.parse_args()

    pcm = await synthesize(args.text)
    if not pcm:
        raise RuntimeError("TTS returned no audio")
    args.output.write_bytes(pcm)
    print(f"wrote {len(pcm)} bytes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
