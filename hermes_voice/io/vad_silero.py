"""Silero VAD adapter: 512-sample 16 kHz int16 frames -> speech probability."""

from __future__ import annotations

from typing import Any

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


class SileroVad:
    def __init__(self) -> None:
        import torch
        from silero_vad import load_silero_vad

        self._torch = torch
        self._model: Any = load_silero_vad()

    def probability(self, frame: bytes) -> float:
        audio = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) != FRAME_SAMPLES:
            return 0.0
        with self._torch.no_grad():
            prob = self._model(self._torch.from_numpy(audio), SAMPLE_RATE)
        return float(prob.item())

    def reset(self) -> None:
        self._model.reset_states()
