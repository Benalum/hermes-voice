"""Kokoro (MLX) TTS adapter. All model access happens on one dedicated thread."""

from __future__ import annotations

import asyncio
import math
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

DEFAULT_MODEL = "mlx-community/Kokoro-82M-bf16"
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0
SAMPLE_RATE = 24000


def _validate_speed(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("HV_KOKORO_SPEED must be a number")
    resolved = float(value)
    if not math.isfinite(resolved) or not 0.5 <= resolved <= 2.0:
        raise ValueError("HV_KOKORO_SPEED must be between 0.5 and 2.0")
    return resolved


class KokoroTts:
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        voice: str = DEFAULT_VOICE,
        speed: float | None = None,
    ) -> None:
        self._model_id = model_id
        self._voice = voice
        raw_speed: object = (
            speed
            if speed is not None
            else float(os.environ.get("HV_KOKORO_SPEED", str(DEFAULT_SPEED)))
        )
        self._speed = _validate_speed(raw_speed)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")
        self._model: Any = None

    def set_speed(self, speed: float) -> None:
        """Change the speed used by future synthesis calls."""
        self._speed = _validate_speed(speed)

    async def warmup(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self._executor, self._load)

    async def synthesize(self, text: str) -> bytes:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._synthesize_sync, text
        )

    def _load(self) -> Any:
        if self._model is None:
            from mlx_audio.tts.utils import load_model

            _patch_sine_gen_length_bug()
            self._model = load_model(self._model_id)
        return self._model

    def _synthesize_sync(self, text: str) -> bytes:
        model = self._load()
        chunks = [
            np.asarray(segment.audio, dtype=np.float32)
            for segment in model.generate(
                text=text,
                voice=self._voice,
                speed=self._speed,
            )
        ]
        if not chunks:
            return b""
        audio = np.concatenate(chunks)
        return bytes(
            (np.clip(audio, -1.0, 1.0) * 32767.0)
            .astype(np.int16)
            .tobytes()
        )


def _patch_sine_gen_length_bug() -> None:
    """mlx-audio <=0.4.4: SineGen's down/up interpolation can round the sine length
    below the uv length (e.g. 36600 vs 36900), crashing on broadcast for certain
    phoneme counts. Zero-pad the sine tail to the uv length (<= a hop, ~12ms)."""
    import mlx.core as mx
    from mlx_audio.tts.models.kokoro import istftnet

    if getattr(istftnet.SineGen, "_hv_patched", False):
        return

    def patched_call(self: Any, f0: Any) -> tuple[Any, Any, Any]:
        fn = f0 * mx.arange(1, self.harmonic_num + 2)[None, None, :]
        sine_waves = self._f02sine(fn) * self.sine_amp
        uv = self._f02uv(f0)
        target = uv.shape[1]
        if sine_waves.shape[1] < target:
            pad = mx.zeros((sine_waves.shape[0], target - sine_waves.shape[1], sine_waves.shape[2]))
            sine_waves = mx.concatenate([sine_waves, pad], axis=1)
        elif sine_waves.shape[1] > target:
            sine_waves = sine_waves[:, :target, :]
        noise_amp = uv * self.noise_std + (1 - uv) * self.sine_amp / 3
        noise = noise_amp * mx.random.normal(sine_waves.shape)
        return sine_waves * uv + noise, uv, noise

    istftnet.SineGen.__call__ = patched_call
    istftnet.SineGen._hv_patched = True
