"""Dependency-injection ports. Adapters in hermes_voice.io implement these;
tests supply fakes. Kit code never imports I/O libraries."""

from __future__ import annotations

from typing import Protocol


class VadPort(Protocol):
    def probability(self, frame: bytes) -> float:
        """Speech probability for one 512-sample 16 kHz int16 frame."""
        ...


class SttPort(Protocol):
    async def transcribe(self, pcm: bytes) -> str:
        """Transcribe a 16 kHz int16 mono utterance."""
        ...


class TtsPort(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to 24 kHz int16 mono PCM."""
        ...


class ResponderPort(Protocol):
    """Where relayed user text goes (parrot echo, or the Telegram relay)."""

    async def send(self, text: str) -> None: ...

    async def reset(self, chat_key: str) -> None: ...
