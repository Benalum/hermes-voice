"""Dedicated Faster-Whisper process used to avoid Intel macOS OpenMP collisions."""

from __future__ import annotations

import argparse
import json
import platform
import struct
import sys
from importlib import metadata
from typing import Any, BinaryIO

_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_BYTES = 256 * 1024 * 1024
_INTEL_MAC_CTRANSLATE2_VERSION = "4.3.1"
_INTEL_MAC_CPU_THREADS = 1


def _is_intel_mac() -> bool:
    return sys.platform == "darwin" and platform.machine().lower() == "x86_64"


def _ctranslate2_cpu_threads() -> int:
    """Use a conservative CPU configuration on Intel macOS."""
    return _INTEL_MAC_CPU_THREADS if _is_intel_mac() else 0


def _validate_ctranslate2_runtime() -> None:
    """Reject Intel macOS CTranslate2 wheels with the known OpenMP conflict."""
    if not _is_intel_mac():
        return

    try:
        installed = metadata.version("ctranslate2")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("CTranslate2 is not installed for the Intel macOS STT worker") from exc

    if installed != _INTEL_MAC_CTRANSLATE2_VERSION:
        raise RuntimeError(
            "Intel macOS requires ctranslate2 "
            f"{_INTEL_MAC_CTRANSLATE2_VERSION}; found {installed}. "
            "Run the locked Hermes Voice dependency installation."
        )


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


def _write_frame(
    stream: BinaryIO,
    payload: bytes,
) -> None:
    if len(payload) > _MAX_FRAME_BYTES:
        raise ValueError(f"Faster-Whisper worker frame is too large: {len(payload)} bytes")

    frame = _FRAME_HEADER.pack(len(payload)) + payload
    offset = 0

    while offset < len(frame):
        written = stream.write(frame[offset:])

        if written is None or written <= 0:
            raise OSError("Faster-Whisper worker pipe write made no progress")

        offset += written

    stream.flush()


def _write_response(
    stream: BinaryIO,
    **response: object,
) -> None:
    payload = json.dumps(
        response,
        ensure_ascii=True,
    ).encode("utf-8")
    _write_frame(stream, payload)


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
        _validate_ctranslate2_runtime()

        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel(
            args.model_id,
            device=args.device,
            compute_type=args.compute_type,
            cpu_threads=_ctranslate2_cpu_threads(),
            num_workers=1,
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
