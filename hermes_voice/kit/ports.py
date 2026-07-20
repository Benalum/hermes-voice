"""Dependency-injection ports. Adapters in hermes_voice.io implement these;
tests supply fakes. Kit code never imports I/O libraries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SpeakerDecision:
    configured: bool
    accepted: bool
    score: float | None
    speaker: str | None
    threshold: float
    reason: str


class SpeakerVerifierPort(Protocol):
    async def verify_speaker(self, pcm: bytes) -> SpeakerDecision:
        """Decide whether a completed 16 kHz utterance matches an enrollment."""
        ...


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

    async def close(self) -> None: ...
