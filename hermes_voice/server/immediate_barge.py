"""Immediate unmuted barge-in for the portable voice orchestrator."""

from __future__ import annotations

import logging

from hermes_voice.kit import session as sm
from hermes_voice.kit.turns import BargeIn, SpeechEnd, SpeechStart
from hermes_voice.server.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class ImmediateBargeInOrchestrator(Orchestrator):
    """Stop agent audio when barge-in is confirmed, then finish the user turn."""

    def feed_audio(self, pcm: bytes) -> None:
        prob = self._vad.probability(pcm)
        muted = self._voice_mute.muted
        speaking = self._session.state is sm.State.SPEAKING
        detect_barge_in = speaking and not muted

        for turn_event in self._turns.feed(
            pcm,
            prob,
            speaking=detect_barge_in,
        ):
            match turn_event:
                case SpeechEnd(pcm=utterance) if self._pending_barge_in:
                    self._pending_barge_in = False
                    self._spawn(self._transcribe(utterance, barge_in=True))
                case SpeechEnd(pcm=utterance) if muted and speaking:
                    # Muted speech can issue command-only controls, but it must not
                    # interrupt audio merely because speech was detected.
                    self._spawn(self._transcribe(utterance, command_only=True))
                case SpeechEnd(pcm=utterance):
                    self.emit(sm.SpeechEnded(pcm=utterance))
                case BargeIn() if detect_barge_in:
                    if not self._pending_barge_in:
                        self._pending_barge_in = True
                        # The TurnManager has already required the configured barge
                        # threshold and frame count. Interrupt now instead of waiting
                        # for SpeechEnd, while retaining the utterance for STT.
                        self.emit(sm.BargedIn())
                        logger.info(
                            "barge-in detected; stopping agent speech immediately "
                            "(threshold=%.2f, frames=%d)",
                            self._config.turn.barge_threshold,
                            self._config.turn.barge_frames,
                        )
                case SpeechStart():
                    pass
