"""Portable Faster-Whisper speech-to-text adapter for Linux and other non-MLX hosts."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

DEFAULT_MODEL = "small.en"

SAMPLE_RATE = 16_000


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

        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="stt",
        )

        self._model: Any = None

    async def warmup(self) -> None:
        """Load the model without blocking the asyncio event loop."""

        await asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._load,
        )

    async def transcribe(self, pcm: bytes) -> str:
        """Return normalized text for one PCM utterance."""

        if not pcm:
            return ""

        # Signed 16-bit samples must contain complete two-byte values.

        if len(pcm) % 2:
            pcm = pcm[:-1]

        if not pcm:
            return ""

        return await asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._transcribe_sync,
            pcm,
        )

    def _load(self) -> Any:

        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_id,
                device=self._device,
                compute_type=self._compute_type,
            )

        return self._model

    def _transcribe_sync(self, pcm: bytes) -> str:

        model = self._load()

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _info = model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=False,
        )

        text_parts = [
            str(segment.text).strip() for segment in segments if str(segment.text).strip()
        ]

        return " ".join(text_parts).strip()
