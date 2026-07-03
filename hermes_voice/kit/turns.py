"""Turn detection: VAD probabilities in, speech_start / speech_end / barge_in events out.

Pure logic - the VAD frame stream is the clock (one feed() call per 32ms frame).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TurnConfig:
    speech_threshold: float = 0.5
    barge_threshold: float = 0.7
    onset_frames: int = 3
    hangover_frames: int = 16
    barge_frames: int = 8
    pre_roll_frames: int = 10


@dataclass(frozen=True)
class SpeechStart:
    pass


@dataclass(frozen=True)
class SpeechEnd:
    pcm: bytes


@dataclass(frozen=True)
class BargeIn:
    pass


TurnEvent = SpeechStart | SpeechEnd | BargeIn


@dataclass
class TurnManager:
    config: TurnConfig
    _pre_roll: deque[bytes] = field(init=False)
    _in_speech: bool = field(default=False, init=False)
    _utterance: list[bytes] = field(default_factory=list, init=False)
    _onset: list[bytes] = field(default_factory=list, init=False)
    _silence_run: int = field(default=0, init=False)
    _barge: list[bytes] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._pre_roll = deque(maxlen=self.config.pre_roll_frames)

    def feed(self, pcm: bytes, prob: float, *, speaking: bool = False) -> tuple[TurnEvent, ...]:
        if self._in_speech:
            return self._feed_in_speech(pcm, prob)
        if speaking:
            return self._feed_while_speaking(pcm, prob)
        return self._feed_idle(pcm, prob)

    def _feed_in_speech(self, pcm: bytes, prob: float) -> tuple[TurnEvent, ...]:
        self._utterance.append(pcm)
        if prob >= self.config.speech_threshold:
            self._silence_run = 0
            return ()
        self._silence_run += 1
        if self._silence_run < self.config.hangover_frames:
            return ()
        utterance = b"".join(self._utterance)
        self._reset()
        return (SpeechEnd(pcm=utterance),)

    def _feed_while_speaking(self, pcm: bytes, prob: float) -> tuple[TurnEvent, ...]:
        if prob < self.config.barge_threshold:
            self._barge.clear()
            return ()
        self._barge.append(pcm)
        if len(self._barge) < self.config.barge_frames:
            return ()
        self._in_speech = True
        self._utterance = list(self._barge)
        self._barge = []
        return (BargeIn(),)

    def _feed_idle(self, pcm: bytes, prob: float) -> tuple[TurnEvent, ...]:
        if prob < self.config.speech_threshold:
            self._pre_roll.extend(self._onset)
            self._onset = []
            self._pre_roll.append(pcm)
            return ()
        self._onset.append(pcm)
        if len(self._onset) < self.config.onset_frames:
            return ()
        self._in_speech = True
        self._utterance = [*self._pre_roll, *self._onset]
        self._pre_roll.clear()
        self._onset = []
        return (SpeechStart(),)

    def _reset(self) -> None:
        self._in_speech = False
        self._utterance = []
        self._onset = []
        self._silence_run = 0
        self._barge = []
