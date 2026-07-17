"""Local spoken mute/unmute command handling.

Speech is still transcribed locally while muted so an enrolled user can say an
unmute phrase. Non-command transcripts are suppressed before they reach the
remote agent or Telegram.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MUTE_PHRASES = frozenset({"mute", "mute me", "stop listening"})
_UNMUTE_PHRASES = frozenset({"unmute", "unmute me", "start listening"})


def _normalize_command(text: str) -> str:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return " ".join(words)


@dataclass(frozen=True)
class MuteResult:
    forward: bool
    status: str | None = None


class VoiceMuteControl:
    def __init__(self, *, muted: bool = False) -> None:
        self.muted = muted

    def handle(self, text: str) -> MuteResult:
        command = _normalize_command(text)

        if not self.muted and command in _MUTE_PHRASES:
            self.muted = True
            return MuteResult(forward=False, status="muted")

        if self.muted and command in _UNMUTE_PHRASES:
            self.muted = False
            return MuteResult(forward=False, status="unmuted")

        return MuteResult(forward=not self.muted)
