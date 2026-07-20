"""Portable Kokoro text-to-speech adapter for Linux and other non-MLX hosts."""

from __future__ import annotations

import asyncio
import math
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

DEFAULT_LANGUAGE = "a"

DEFAULT_VOICE = "af_heart"

DEFAULT_SPEED = 1.0

SAMPLE_RATE = 24_000


def _validate_speed(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("HV_KOKORO_SPEED must be a number")
    resolved = float(value)
    if not math.isfinite(resolved) or not 0.5 <= resolved <= 2.0:
        raise ValueError("HV_KOKORO_SPEED must be between 0.5 and 2.0")
    return resolved


class PortableKokoroTts:
    """Synthesize text as 24 kHz, mono, signed 16-bit PCM."""

    def __init__(
        self,
        *,
        language_code: str | None = None,
        voice: str | None = None,
        speed: float | None = None,
    ) -> None:

        self._language_code = language_code or os.environ.get(
            "HV_KOKORO_LANGUAGE",
            DEFAULT_LANGUAGE,
        )

        self._voice = voice or os.environ.get(
            "HV_KOKORO_VOICE",
            DEFAULT_VOICE,
        )

        raw_speed = (
            str(speed)
            if speed is not None
            else os.environ.get("HV_KOKORO_SPEED", str(DEFAULT_SPEED))
        )

        try:
            self._speed = _validate_speed(float(raw_speed))
        except ValueError as exc:
            raise ValueError("HV_KOKORO_SPEED must be between 0.5 and 2.0") from exc

        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="tts",
        )

        self._pipeline: Any = None

    def set_speed(self, speed: float) -> None:
        """Change the speed used by future synthesis calls."""
        self._speed = _validate_speed(speed)

    async def warmup(self) -> None:
        """Load Kokoro without blocking the asyncio event loop."""

        await asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._load,
        )

    async def synthesize(self, text: str) -> bytes:
        """Return 24 kHz mono int16 PCM for the supplied text."""

        normalized = text.strip()

        if not normalized:
            return b""

        return await asyncio.get_running_loop().run_in_executor(
            self._executor,
            self._synthesize_sync,
            normalized,
        )

    def _load(self) -> Any:

        if self._pipeline is None:
            from kokoro import KPipeline

            self._pipeline = KPipeline(
                lang_code=self._language_code,
            )

        return self._pipeline

    def _synthesize_sync(self, text: str) -> bytes:

        pipeline = self._load()

        chunks: list[np.ndarray[Any, np.dtype[np.float32]]] = []

        for _graphemes, _phonemes, audio in pipeline(
            text,
            voice=self._voice,
            speed=self._speed,
        ):
            chunk = np.asarray(audio, dtype=np.float32).reshape(-1)

            if chunk.size:
                chunks.append(chunk)

        if not chunks:
            return b""

        combined = np.concatenate(chunks)

        clipped = np.clip(combined, -1.0, 1.0)

        return bytes((clipped * 32767.0).astype(np.int16).tobytes())
