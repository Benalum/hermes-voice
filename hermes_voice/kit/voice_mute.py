"""Local spoken mute/unmute command handling.

Speech is still transcribed locally while command-muted so an enrolled user can
say an unmute phrase. Non-command transcripts are suppressed before they reach
the remote agent or Telegram.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WAKE_PREFIX = r"(?:(?:hey|ok|okay)\s+)?(?:hermes\s+)?"
_REQUEST_PREFIX = r"(?:(?:please\s+)|(?:(?:can|could|would)\s+you\s+))?"
_POLITE_SUFFIX = r"(?:\s+please)?"
# Short filler that Whisper often prepends to a command ("no, mute me",
# "yeah mute me"). Kept tiny so a sentence merely *about* muting still
# forwards (see test_incidental_mute_phrase_does_not_toggle).
_LEADING_FILLER = r"(?:(?:no|yes|yeah|now|just|but)\s+)?"
# "mute myself" / "unmute myself" (and sloppy "my self") are common ways to
# phrase the command; treat them identically to "mute me" / "unmute me".
_MYSELF = r"(?:me|myself|my\s*self)"

_MUTE_PATTERN = re.compile(
    rf"^{_WAKE_PREFIX}{_LEADING_FILLER}{_REQUEST_PREFIX}"
    rf"(?:mute(?:\s+{_MYSELF})?|stop\s+listening(?:\s+to\s+{_MYSELF})?)"
    rf"{_POLITE_SUFFIX}$"
)
_UNMUTE_PATTERN = re.compile(
    rf"^{_WAKE_PREFIX}{_LEADING_FILLER}{_REQUEST_PREFIX}"
    rf"(?:unmute(?:\s+{_MYSELF})?|start\s+listening(?:\s+to\s+{_MYSELF})?|listen\s+to\s+{_MYSELF})"
    rf"{_POLITE_SUFFIX}$"
)


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

    def set_muted(self, muted: bool) -> MuteResult:
        self.muted = bool(muted)
        return MuteResult(
            forward=False,
            status="muted" if self.muted else "unmuted",
        )

    def handle(self, text: str) -> MuteResult:
        command = _normalize_command(text)

        if not self.muted and _MUTE_PATTERN.fullmatch(command):
            return self.set_muted(True)

        if self.muted and _UNMUTE_PATTERN.fullmatch(command):
            return self.set_muted(False)

        return MuteResult(forward=not self.muted)
