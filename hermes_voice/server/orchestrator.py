"""Thin async glue: WS frames -> VAD -> turns -> session machine -> STT/TTS/responder.

All state decisions live in the pure kit; this module only interprets effects.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from hermes_voice.kit import session as sm
from hermes_voice.kit.normalize import normalize_for_speech
from hermes_voice.kit.ports import ResponderPort, SttPort, TtsPort, VadPort
from hermes_voice.kit.protocol import (
    AgentText,
    ServerMsg,
    SpeakStart,
    SpeakStop,
    StateMsg,
    Transcript,
    encode_audio_frame,
    encode_server_msg,
)
from hermes_voice.kit.turns import BargeIn, SpeechEnd, SpeechStart, TurnConfig, TurnManager

logger = logging.getLogger(__name__)

TTS_SAMPLE_RATE = 24000


@dataclass(frozen=True)
class OrchestratorConfig:
    turn: TurnConfig = field(default_factory=TurnConfig)
    wait_timeout_s: float = 180.0
    wait_timeouts: Mapping[str, float] | None = None

    def timeout_for(self, chat_key: str | None) -> float:
        if self.wait_timeouts is not None and chat_key is not None:
            return self.wait_timeouts.get(chat_key, self.wait_timeout_s)
        return self.wait_timeout_s


class Orchestrator:
    def __init__(
        self,
        *,
        send_text: Callable[[str], Awaitable[None]],
        send_bytes: Callable[[bytes], Awaitable[None]],
        vad: VadPort,
        stt: SttPort,
        tts: TtsPort,
        make_responder: Callable[[Callable[[sm.Event], None]], ResponderPort],
        initial_chat: str,
        config: OrchestratorConfig | None = None,
    ) -> None:
        config = config or OrchestratorConfig()
        self._send_text = send_text
        self._send_bytes = send_bytes
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._config = config
        self._session = sm.Session(state=sm.State.LISTENING, turn_open=False, chat_key=initial_chat)
        self._turns = TurnManager(config.turn)
        self._events: asyncio.Queue[sm.Event] = asyncio.Queue()
        self._epoch = 1
        self._speech_texts: deque[str] = deque()
        self._tts_task: asyncio.Task[None] | None = None
        self._wait_timer: asyncio.Task[None] | None = None
        self._side_tasks: set[asyncio.Task[None]] = set()
        self._responder = make_responder(self.emit)

    # --- inputs ---

    def emit(self, event: sm.Event) -> None:
        self._events.put_nowait(event)

    def feed_audio(self, pcm: bytes) -> None:
        prob = self._vad.probability(pcm)
        speaking = self._session.state is sm.State.SPEAKING
        for turn_event in self._turns.feed(pcm, prob, speaking=speaking):
            match turn_event:
                case SpeechEnd(pcm=utterance):
                    self.emit(sm.SpeechEnded(pcm=utterance))
                case BargeIn():
                    self.emit(sm.BargedIn())
                case SpeechStart():
                    pass

    # --- main loop ---

    async def run(self) -> None:
        await self._responder.reset(self._session.chat_key or "")
        try:
            while True:
                event = await self._events.get()
                await self._handle(event)
        finally:
            self._shutdown()

    async def _handle(self, event: sm.Event) -> None:
        before = self._session
        self._session, effects = sm.advance(self._session, event)
        for effect in effects:
            await self._apply(effect)
        if self._session.state is not before.state:
            await self._send(StateMsg(name=self._session.state.value))
        self._manage_wait_timer()

    async def _apply(self, effect: sm.Effect) -> None:
        match effect:
            case sm.Transcribe(pcm=pcm):
                self._spawn(self._transcribe(pcm))
            case sm.SendTranscript(text=text):
                await self._send(Transcript(role="user", text=text, final=True))
            case sm.RelaySend(text=text):
                self._spawn(self._relay_send(text))
            case sm.SendAgentText(text=text, message_id=message_id):
                await self._send(AgentText(text=text, message_id=message_id))
            case sm.EnqueueSpeech(text=text):
                self._enqueue_speech(text)
            case sm.StopSpeaking():
                await self._stop_speaking()
            case sm.ResetReplies(chat_key=chat_key):
                self._speech_texts.clear()
                self._spawn(self._responder.reset(chat_key))

    # --- effect implementations ---

    async def _transcribe(self, pcm: bytes) -> None:
        try:
            text = await self._stt.transcribe(pcm)
        except Exception:
            logger.exception("STT failed")
            text = ""
        self.emit(sm.SttCompleted(text=text))

    async def _relay_send(self, text: str) -> None:
        try:
            await self._responder.send(text)
        except Exception:
            logger.exception("responder send failed")

    def _enqueue_speech(self, text: str) -> None:
        sentences = [s for s in self._split_speech(text) if s]
        if not sentences:
            self.emit(sm.TtsFinished())
            return
        self._speech_texts.extend(sentences)
        if self._tts_task is None or self._tts_task.done():
            self._tts_task = asyncio.create_task(self._tts_worker())

    @staticmethod
    def _split_speech(text: str) -> tuple[str, ...]:
        from hermes_voice.kit.sentences import split_sentences

        return split_sentences(normalize_for_speech(text))

    async def _tts_worker(self) -> None:
        epoch = self._epoch
        await self._send(SpeakStart(epoch=epoch, sample_rate=TTS_SAMPLE_RATE))
        while self._speech_texts:
            text = self._speech_texts.popleft()
            try:
                pcm = await self._tts.synthesize(text)
            except Exception:
                logger.exception("TTS failed for %r", text)
                continue
            if self._epoch != epoch:
                return
            await self._send_bytes(encode_audio_frame(epoch=epoch, pcm=pcm))
        await self._send(SpeakStop(epoch=epoch))
        self.emit(sm.TtsFinished())

    async def _stop_speaking(self) -> None:
        old_epoch = self._epoch
        self._epoch += 1
        self._speech_texts.clear()
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tts_task
        self._tts_task = None
        await self._send(SpeakStop(epoch=old_epoch))

    def _manage_wait_timer(self) -> None:
        should_run = self._session.state is sm.State.WAITING and self._session.turn_open
        running = self._wait_timer is not None and not self._wait_timer.done()
        if should_run and not running:
            self._wait_timer = asyncio.create_task(self._wait_timeout())
        elif not should_run and running and self._wait_timer is not None:
            self._wait_timer.cancel()
            self._wait_timer = None

    async def _wait_timeout(self) -> None:
        await asyncio.sleep(self._config.timeout_for(self._session.chat_key))
        self.emit(sm.MaxWaitTimedOut())

    # --- plumbing ---

    async def _send(self, msg: ServerMsg) -> None:
        await self._send_text(encode_server_msg(msg))

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._side_tasks.add(task)
        task.add_done_callback(self._side_tasks.discard)

    def _shutdown(self) -> None:
        for task in (self._tts_task, self._wait_timer, *self._side_tasks):
            if task is not None and not task.done():
                task.cancel()
        close = getattr(self._responder, "close", None)
        if callable(close):
            close()


class ParrotResponder:
    """M2 responder: echoes the user's words back as if an agent replied."""

    def __init__(self, emit: Callable[[sm.Event], None]) -> None:
        self._emit = emit

    async def send(self, text: str) -> None:
        self._emit(sm.AgentSpeakable(text=text, message_id=0))
        self._emit(sm.TurnSettled())

    async def reset(self, chat_key: str) -> None:
        return None
