"""Parakeet (MLX) STT adapter. All model access happens on one dedicated thread."""

from __future__ import annotations

import asyncio
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v2"
SAMPLE_RATE = 16000


class ParakeetStt:
    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self._model_id = model_id
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._model: Any = None

    async def warmup(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self._executor, self._load)

    async def transcribe(self, pcm: bytes) -> str:
        return await asyncio.get_running_loop().run_in_executor(
            self._executor, self._transcribe_sync, pcm
        )

    def _load(self) -> Any:
        if self._model is None:
            from parakeet_mlx import from_pretrained

            self._model = from_pretrained(self._model_id)
        return self._model

    def _transcribe_sync(self, pcm: bytes) -> str:
        model = self._load()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete_on_close=False) as tmp:
            tmp.close()
            _write_wav(Path(tmp.name), pcm)
            result = model.transcribe(tmp.name)
        return str(result.text).strip()


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)
