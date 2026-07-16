"""Portable Faster-Whisper speech-to-text adapter for Linux and other non-MLX hosts."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, IO

import numpy as np

DEFAULT_MODEL = "small.en"
SAMPLE_RATE = 16_000
_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_BYTES = 256 * 1024 * 1024


def _needs_process_isolation() -> bool:
    """Keep CTranslate2 in a dedicated interpreter on Intel macOS."""
    return sys.platform == "darwin" and platform.machine().lower() == "x86_64"


def _new_model(model_id: str, device: str, compute_type: str) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_id,
        device=device,
        compute_type=compute_type,
    )


def _transcribe_model(model: Any, pcm: bytes) -> str:
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = model.transcribe(
        audio,
        language="en",
        beam_size=1,
        vad_filter=False,
    )
    text_parts = [str(segment.text).strip() for segment in segments if str(segment.text).strip()]
    return " ".join(text_parts).strip()


def _read_exact(stream: IO[bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("Faster-Whisper worker closed its output stream")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_frame(stream: IO[bytes]) -> bytes:
    header = _read_exact(stream, _FRAME_HEADER.size)
    (size,) = _FRAME_HEADER.unpack(header)
    if size > _MAX_FRAME_BYTES:
        raise RuntimeError(f"Faster-Whisper worker frame is too large: {size} bytes")
    return _read_exact(stream, size) if size else b""


def _write_frame(stream: IO[bytes], payload: bytes) -> None:
    if len(payload) > _MAX_FRAME_BYTES:
        raise ValueError(f"Faster-Whisper worker frame is too large: {len(payload)} bytes")
    stream.write(_FRAME_HEADER.pack(len(payload)))
    stream.write(payload)
    stream.flush()


def _decode_worker_response(payload: bytes) -> dict[str, object]:
    try:
        response = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Faster-Whisper worker returned an invalid response") from exc
    if not isinstance(response, dict):
        raise RuntimeError("Faster-Whisper worker returned a non-object response")
    return response


class _IsolatedFasterWhisperWorker:
    """Long-lived Intel macOS STT worker that never imports the parent application."""

    def __init__(self, model_id: str, device: str, compute_type: str) -> None:
        self._model_id = model_id
        self._device = device
        self._compute_type = compute_type
        self._process: subprocess.Popen[bytes] | None = None

    def _command(self) -> list[str]:
        return [
            sys.executable,
            "-I",
            "-m",
            "hermes_voice.io.stt_faster_whisper_worker",
            "--model-id",
            self._model_id,
            "--device",
            self._device,
            "--compute-type",
            self._compute_type,
        ]

    def _start(self) -> subprocess.Popen[bytes]:
        process = self._process
        if process is not None and process.poll() is None:
            return process

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            self._command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0,
            env=env,
        )
        self._process = process

        try:
            response = self._receive(process)
        except Exception:
            self.close()
            raise
        if response.get("status") != "ready":
            self.close()
            message = response.get("message", "unknown startup failure")
            raise RuntimeError(f"Faster-Whisper worker failed to start: {message}")
        return process

    def _receive(self, process: subprocess.Popen[bytes]) -> dict[str, object]:
        if process.stdout is None:
            raise RuntimeError("Faster-Whisper worker stdout is unavailable")
        try:
            return _decode_worker_response(_read_frame(process.stdout))
        except EOFError as exc:
            code = process.poll()
            raise RuntimeError(
                f"Faster-Whisper worker exited unexpectedly with code {code}"
            ) from exc

    def warmup(self) -> None:
        self._start()

    def transcribe(self, pcm: bytes) -> str:
        process = self._start()
        if process.stdin is None:
            raise RuntimeError("Faster-Whisper worker stdin is unavailable")
        _write_frame(process.stdin, pcm)
        response = self._receive(process)
        if response.get("status") != "ok":
            message = response.get("message", "unknown transcription failure")
            raise RuntimeError(f"Faster-Whisper worker failed: {message}")
        text = response.get("text", "")
        if not isinstance(text, str):
            raise RuntimeError("Faster-Whisper worker returned non-text output")
        return text.strip()

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return

        if process.poll() is None and process.stdin is not None:
            try:
                _write_frame(process.stdin, b"")
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


class FasterWhisperStt:
    """Transcribe 16 kHz, mono, signed 16-bit PCM using Faster-Whisper."""

    def __init__(
        self,
        model_id: str | None = None,
        *,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self._model_id = model_id or os.environ.get(
            "HV_WHISPER_MODEL",
            DEFAULT_MODEL,
        )
        self._device = device or os.environ.get(
            "HV_WHISPER_DEVICE",
            "cpu",
        )
        self._compute_type = compute_type or os.environ.get(
            "HV_WHISPER_COMPUTE_TYPE",
            "int8",
        )
        self._process_isolated = _needs_process_isolation()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="stt",
        )
        self._worker = (
            _IsolatedFasterWhisperWorker(
                self._model_id,
                self._device,
                self._compute_type,
            )
            if self._process_isolated
            else None
        )
        self._model: Any = None

    async def warmup(self) -> None:
        """Load the model without blocking the asyncio event loop."""
        target = self._worker.warmup if self._worker is not None else self._load
        await asyncio.get_running_loop().run_in_executor(self._executor, target)

    async def transcribe(self, pcm: bytes) -> str:
        """Return normalized text for one PCM utterance."""
        if not pcm:
            return ""

        # Signed 16-bit samples must contain complete two-byte values.
        if len(pcm) % 2:
            pcm = pcm[:-1]
        if not pcm:
            return ""

        target = self._worker.transcribe if self._worker is not None else self._transcribe_sync
        return await asyncio.get_running_loop().run_in_executor(
            self._executor,
            target,
            pcm,
        )

    def _load(self) -> Any:
        if self._model is None:
            self._model = _new_model(
                self._model_id,
                self._device,
                self._compute_type,
            )
        return self._model

    def _transcribe_sync(self, pcm: bytes) -> str:
        return _transcribe_model(self._load(), pcm)

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        if self._worker is not None:
            self._worker.close()
