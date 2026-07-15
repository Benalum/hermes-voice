"""Portable Faster-Whisper speech-to-text adapter for Linux and other non-MLX hosts."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import platform
import sys
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any

import numpy as np

DEFAULT_MODEL = "small.en"

SAMPLE_RATE = 16_000

_PROCESS_MODEL: Any = None


def _needs_process_isolation() -> bool:
    """Keep CTranslate2 out of the PyTorch process on Intel macOS."""
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


def _process_warmup(model_id: str, device: str, compute_type: str) -> None:
    global _PROCESS_MODEL
    if _PROCESS_MODEL is None:
        _PROCESS_MODEL = _new_model(model_id, device, compute_type)


def _process_transcribe(
    model_id: str,
    device: str,
    compute_type: str,
    pcm: bytes,
) -> str:
    _process_warmup(model_id, device, compute_type)
    return _transcribe_model(_PROCESS_MODEL, pcm)


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
        self._executor: Executor
        if self._process_isolated:
            self._executor = ProcessPoolExecutor(
                max_workers=1,
                mp_context=multiprocessing.get_context("spawn"),
            )
        else:
            self._executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="stt",
            )

        self._model: Any = None

    async def warmup(self) -> None:
        """Load the model without blocking the asyncio event loop."""
        loop = asyncio.get_running_loop()
        if self._process_isolated:
            await loop.run_in_executor(
                self._executor,
                _process_warmup,
                self._model_id,
                self._device,
                self._compute_type,
            )
            return
        await loop.run_in_executor(self._executor, self._load)

    async def transcribe(self, pcm: bytes) -> str:
        """Return normalized text for one PCM utterance."""
        if not pcm:
            return ""

        # Signed 16-bit samples must contain complete two-byte values.
        if len(pcm) % 2:
            pcm = pcm[:-1]
        if not pcm:
            return ""

        loop = asyncio.get_running_loop()
        if self._process_isolated:
            return await loop.run_in_executor(
                self._executor,
                _process_transcribe,
                self._model_id,
                self._device,
                self._compute_type,
                pcm,
            )
        return await loop.run_in_executor(
            self._executor,
            self._transcribe_sync,
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
