"""Dedicated Faster-Whisper process used to avoid Intel macOS OpenMP collisions."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from typing import Any, BinaryIO

_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_BYTES = 256 * 1024 * 1024


def _read_exact(stream: BinaryIO, size: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if remaining == size:
                return None
            raise EOFError("parent closed a partial Faster-Whisper worker frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_frame(stream: BinaryIO) -> bytes | None:
    header = _read_exact(stream, _FRAME_HEADER.size)
    if header is None:
        return None
    (size,) = _FRAME_HEADER.unpack(header)
    if size > _MAX_FRAME_BYTES:
        raise RuntimeError(f"parent frame is too large: {size} bytes")
    if size == 0:
        return b""
    payload = _read_exact(stream, size)
    if payload is None:
        raise EOFError("parent closed before sending the worker frame payload")
    return payload


def _write_response(stream: BinaryIO, **response: object) -> None:
    payload = json.dumps(response, ensure_ascii=True).encode("utf-8")
    stream.write(_FRAME_HEADER.pack(len(payload)))
    stream.write(payload)
    stream.flush()


def _transcribe(model: Any, pcm: bytes) -> str:
    # Faster-Whisper imports CTranslate2 before NumPy. Preserve that order
    # on Intel macOS to avoid initializing competing OpenMP runtimes.
    import numpy as np

    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = model.transcribe(
        audio,
        language="en",
        beam_size=1,
        vad_filter=False,
    )
    text_parts = [str(segment.text).strip() for segment in segments if str(segment.text).strip()]
    return " ".join(text_parts).strip()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--compute-type", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel(
            args.model_id,
            device=args.device,
            compute_type=args.compute_type,
        )
    except Exception as exc:
        _write_response(stdout, status="error", message=f"{type(exc).__name__}: {exc}")
        return 1

    _write_response(stdout, status="ready")
    while True:
        try:
            pcm = _read_frame(stdin)
        except Exception as exc:
            _write_response(stdout, status="error", message=f"{type(exc).__name__}: {exc}")
            return 2

        if pcm is None or not pcm:
            return 0

        try:
            text = _transcribe(model, pcm)
        except Exception as exc:
            _write_response(stdout, status="error", message=f"{type(exc).__name__}: {exc}")
            continue
        _write_response(stdout, status="ok", text=text)


if __name__ == "__main__":
    raise SystemExit(main())
