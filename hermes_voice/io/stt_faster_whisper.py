"""Portable Faster-Whisper speech-to-text adapter for Linux and other non-MLX hosts."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import platform
import select
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import IO, Any

import numpy as np

DEFAULT_MODEL = "small.en"
SAMPLE_RATE = 16_000
_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_BYTES = 256 * 1024 * 1024
DEFAULT_WORKER_START_TIMEOUT_S = 1_200.0
DEFAULT_WORKER_TRANSCRIBE_TIMEOUT_S = 300.0
DEFAULT_WORKER_SHUTDOWN_TIMEOUT_S = 5.0


def _positive_timeout(value: float, *, setting: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved) or resolved <= 0:
        raise ValueError(f"{setting} must be a finite positive number")
    return resolved


def _timeout_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return _positive_timeout(float(raw), setting=name)
    except ValueError as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc


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


def _read_exact_until(
    stream: IO[bytes],
    size: int,
    *,
    deadline: float,
) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError("timed out waiting for Faster-Whisper worker output")
        readable, _writable, _exceptional = select.select(
            [stream],
            [],
            [],
            timeout,
        )
        if not readable:
            raise TimeoutError("timed out waiting for Faster-Whisper worker output")
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("Faster-Whisper worker closed its output stream")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_frame_with_timeout(
    stream: IO[bytes],
    timeout_s: float,
) -> bytes:
    deadline = time.monotonic() + _positive_timeout(
        timeout_s,
        setting="worker response timeout",
    )
    header = _read_exact_until(
        stream,
        _FRAME_HEADER.size,
        deadline=deadline,
    )
    (size,) = _FRAME_HEADER.unpack(header)
    if size > _MAX_FRAME_BYTES:
        raise RuntimeError(f"Faster-Whisper worker frame is too large: {size} bytes")
    if not size:
        return b""
    return _read_exact_until(
        stream,
        size,
        deadline=deadline,
    )


def _write_frame(stream: IO[bytes], payload: bytes) -> None:
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

    def __init__(
        self,
        model_id: str,
        device: str,
        compute_type: str,
        *,
        start_timeout_s: float = DEFAULT_WORKER_START_TIMEOUT_S,
        transcribe_timeout_s: float = DEFAULT_WORKER_TRANSCRIBE_TIMEOUT_S,
        shutdown_timeout_s: float = DEFAULT_WORKER_SHUTDOWN_TIMEOUT_S,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._compute_type = compute_type
        self._start_timeout_s = _positive_timeout(
            start_timeout_s,
            setting="worker startup timeout",
        )
        self._transcribe_timeout_s = _positive_timeout(
            transcribe_timeout_s,
            setting="worker transcription timeout",
        )
        self._shutdown_timeout_s = _positive_timeout(
            shutdown_timeout_s,
            setting="worker shutdown timeout",
        )
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
            response = self._receive(
                process,
                timeout_s=self._start_timeout_s,
                operation="startup",
            )
        except Exception:
            with contextlib.suppress(Exception):
                self.close()
            raise
        if response.get("status") != "ready":
            self.close()
            message = response.get("message", "unknown startup failure")
            raise RuntimeError(f"Faster-Whisper worker failed to start: {message}")
        return process

    def _receive(
        self,
        process: subprocess.Popen[bytes],
        *,
        timeout_s: float,
        operation: str,
    ) -> dict[str, object]:
        if process.stdout is None:
            raise RuntimeError("Faster-Whisper worker stdout is unavailable")
        try:
            payload = _read_frame_with_timeout(
                process.stdout,
                timeout_s,
            )
            return _decode_worker_response(payload)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Faster-Whisper worker {operation} timed out after {timeout_s:g} seconds"
            ) from exc
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
        try:
            response = self._receive(
                process,
                timeout_s=self._transcribe_timeout_s,
                operation="transcription",
            )
        except TimeoutError:
            with contextlib.suppress(Exception):
                self.close()
            raise
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
            process.wait(timeout=self._shutdown_timeout_s)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=self._shutdown_timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=self._shutdown_timeout_s)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError("Faster-Whisper worker did not exit after kill") from exc
        finally:
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()


class FasterWhisperStt:
    """Transcribe 16 kHz, mono, signed 16-bit PCM using Faster-Whisper."""

    def __init__(
        self,
        model_id: str | None = None,
        *,
        device: str | None = None,
        compute_type: str | None = None,
        worker_start_timeout_s: float | None = None,
        worker_transcribe_timeout_s: float | None = None,
        worker_shutdown_timeout_s: float | None = None,
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
        self._worker_start_timeout_s = DEFAULT_WORKER_START_TIMEOUT_S
        self._worker_transcribe_timeout_s = DEFAULT_WORKER_TRANSCRIBE_TIMEOUT_S
        self._worker_shutdown_timeout_s = DEFAULT_WORKER_SHUTDOWN_TIMEOUT_S
        if self._process_isolated:
            self._worker_start_timeout_s = (
                _positive_timeout(
                    worker_start_timeout_s,
                    setting="worker startup timeout",
                )
                if worker_start_timeout_s is not None
                else _timeout_from_env(
                    "HV_WHISPER_WORKER_START_TIMEOUT_S",
                    DEFAULT_WORKER_START_TIMEOUT_S,
                )
            )
            self._worker_transcribe_timeout_s = (
                _positive_timeout(
                    worker_transcribe_timeout_s,
                    setting="worker transcription timeout",
                )
                if worker_transcribe_timeout_s is not None
                else _timeout_from_env(
                    "HV_WHISPER_WORKER_TRANSCRIBE_TIMEOUT_S",
                    DEFAULT_WORKER_TRANSCRIBE_TIMEOUT_S,
                )
            )
            self._worker_shutdown_timeout_s = (
                _positive_timeout(
                    worker_shutdown_timeout_s,
                    setting="worker shutdown timeout",
                )
                if worker_shutdown_timeout_s is not None
                else _timeout_from_env(
                    "HV_WHISPER_WORKER_SHUTDOWN_TIMEOUT_S",
                    DEFAULT_WORKER_SHUTDOWN_TIMEOUT_S,
                )
            )
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="stt",
        )
        self._worker = (
            _IsolatedFasterWhisperWorker(
                self._model_id,
                self._device,
                self._compute_type,
                start_timeout_s=self._worker_start_timeout_s,
                transcribe_timeout_s=self._worker_transcribe_timeout_s,
                shutdown_timeout_s=self._worker_shutdown_timeout_s,
            )
            if self._process_isolated
            else None
        )
        self._model: Any = None
        self._closed = False

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
        if self._closed:
            return
        self._closed = True

        worker_error: Exception | None = None
        if self._worker is not None:
            try:
                self._worker.close()
            except Exception as exc:
                worker_error = exc

        self._executor.shutdown(
            wait=worker_error is None,
            cancel_futures=True,
        )
        if worker_error is not None:
            raise worker_error
