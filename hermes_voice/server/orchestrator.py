"""Thin async glue: WS frames -> VAD -> turns -> session machine -> STT/TTS/responder.

All state decisions live in the pure kit; this module only interprets effects.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hermes_voice.kit import session as sm
from hermes_voice.kit.normalize import normalize_for_speech
from hermes_voice.kit.ports import ResponderPort, SttPort, TtsPort, VadPort
from hermes_voice.kit.speaker_gate import SpeakerGate
from hermes_voice.kit.voice_mute import VoiceMuteControl
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
TTS_SAMPLE_WIDTH_BYTES = 2
TTS_FRAME_MS = 50
TTS_FRAME_BYTES = TTS_SAMPLE_RATE * TTS_SAMPLE_WIDTH_BYTES * TTS_FRAME_MS // 1000
TTS_PLAYBACK_GRACE_S = 0.15


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
        speaker_gate: "SpeakerGate | None" = None,
    ) -> None:
        config = config or OrchestratorConfig()
        self._send_text = send_text
        self._send_bytes = send_bytes
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._speaker_gate = speaker_gate
        self._voice_mute = VoiceMuteControl()
        self._config = config
        self._session = sm.Session(state=sm.State.LISTENING, turn_open=False, chat_key=initial_chat)
        self._turns = TurnManager(config.turn)
        self._events: asyncio.Queue[tuple[sm.Event, asyncio.Future[None] | None]] = asyncio.Queue()
        self._ready = asyncio.Event()
        self._stopped = asyncio.Event()
        self._failure: Exception | None = None
        self._epoch = 1
        self._speech_texts: deque[str] = deque()
        self._tts_task: asyncio.Task[None] | None = None
        self._wait_timer: asyncio.Task[None] | None = None
        self._side_tasks: set[asyncio.Task[None]] = set()
        self._responder = make_responder(self.emit)

    # --- inputs ---

    def emit(self, event: sm.Event) -> None:
        if not self._stopped.is_set():
            self._events.put_nowait((event, None))

    async def dispatch(self, event: sm.Event) -> None:
        """Process a control event and wait for all of its effects to finish."""
        await self._wait_until_ready()
        self._raise_if_stopped()
        future = asyncio.get_running_loop().create_future()
        self._events.put_nowait((event, future))
        await future

    async def list_topics(self, *, query: str = "", limit: int = 100) -> tuple[Any, ...]:
        await self._wait_until_ready()
        self._raise_if_stopped()
        method = getattr(self._responder, "list_topics", None)
        if not callable(method):
            raise RuntimeError("the active responder does not support Telegram topics")
        return tuple(await method(query=query, limit=limit))

    async def select_topic(self, topic_id: int) -> None:
        await self._wait_until_ready()
        self._raise_if_stopped()
        method = getattr(self._responder, "select_topic", None)
        if not callable(method):
            raise RuntimeError("the active responder does not support Telegram topics")
        await method(topic_id)

    async def load_topic_history(
        self,
        topic_id: int,
        *,
        limit: int = 50,
    ) -> tuple[Any, ...]:
        await self._wait_until_ready()
        self._raise_if_stopped()
        method = getattr(self._responder, "load_topic_history", None)
        if not callable(method):
            raise RuntimeError("the active responder does not support Telegram topics")
        return tuple(await method(topic_id, limit=limit))

    def feed_audio(self, pcm: bytes) -> None:
        prob = self._vad.probability(pcm)
        speaking = self._session.state is sm.State.SPEAKING
        for turn_event in self._turns.feed(pcm, prob, speaking=speaking):
            match turn_event:
                case SpeechEnd(pcm=utterance):
                    self.emit(sm.SpeechEnded(pcm=utterance))
                case BargeIn():
                    logger.info(
                        "barge-in detected while speaking (threshold=%.2f, frames=%d)",
                        self._config.turn.barge_threshold,
                        self._config.turn.barge_frames,
                    )
                    self.emit(sm.BargedIn())
                case SpeechStart():
                    pass

    # --- main loop ---

    async def run(self) -> None:
        try:
            await self._responder.reset(self._session.chat_key or "")
            self._ready.set()
            while True:
                event, future = await self._events.get()
                try:
                    await self._handle(event)
                except Exception as exc:
                    if future is None:
                        raise
                    if not future.done():
                        future.set_exception(exc)
                else:
                    if future is not None and not future.done():
                        future.set_result(None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._failure = exc
            raise
        finally:
            self._stopped.set()
            self._fail_pending_dispatches()
            await self._shutdown()

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
                await self._responder.reset(chat_key)

    # --- effect implementations ---

    async def _transcribe(self, pcm: bytes) -> None:
        # Speaker gate: drop utterances that are not from an enrolled voice
        # before they reach STT. Runs in a worker thread (resemblyzer is sync).
        if self._speaker_gate is not None and self._speaker_gate.is_configured:
            try:
                embedding = await asyncio.to_thread(self._speaker_gate.embed, pcm)
                if embedding is not None:
                    accepted, score, speaker = self._speaker_gate.verify(embedding)
                    if not accepted:
                        logger.info(
                            "speaker_gate: REJECTED (score=%.3f < %.3f, speakers=%s)",
                            score,
                            self._speaker_gate._config.threshold,
                            self._speaker_gate.enrolled_names,
                        )
                        self.emit(sm.SttCompleted(text=""))
                        return
                    logger.info(
                        "speaker_gate: accepted (score=%.3f, speaker=%s)", score, speaker
                    )
            except Exception:
                logger.exception("speaker_gate: verification error (failing open)")
        try:
            text = await self._stt.transcribe(pcm)
        except Exception:
            logger.exception("STT failed")
            text = ""

        mute_result = self._voice_mute.handle(text)
        if not mute_result.forward:
            if mute_result.status == "muted":
                await self._send(Transcript(role="system", text="Voice muted", final=True))
                logger.info("voice control: muted; subsequent speech stays local")
            elif mute_result.status == "unmuted":
                await self._send(Transcript(role="system", text="Voice unmuted", final=True))
                logger.info("voice control: unmuted")
            self.emit(sm.SttCompleted(text=""))
            return
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
        next_pcm: asyncio.Task[bytes] | None = None
        try:
            while True:
                while self._speech_texts or next_pcm is not None:
                    if next_pcm is None:
                        text = self._speech_texts.popleft()
                        next_pcm = asyncio.create_task(self._synthesize_safely(text))

                    pcm = await next_pcm
                    next_pcm = None
                    if self._epoch != epoch:
                        return

                    # Prefetch the next sentence while the current PCM plays. This
                    # preserves the original low-gap behavior without flooding the
                    # browser faster than real time.
                    if self._speech_texts:
                        next_text = self._speech_texts.popleft()
                        next_pcm = asyncio.create_task(self._synthesize_safely(next_text))

                    await self._stream_pcm(epoch, pcm)
                    if self._epoch != epoch:
                        return

                # Allow a message that arrives at the end of the current chunk to
                # join the same speaking turn instead of being stranded in the queue.
                await asyncio.sleep(TTS_PLAYBACK_GRACE_S)
                if self._epoch != epoch:
                    return
                if not self._speech_texts:
                    break

            await self._send(SpeakStop(epoch=epoch, flush=False))
            self.emit(sm.TtsFinished())
        finally:
            if next_pcm is not None:
                if not next_pcm.done():
                    next_pcm.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await next_pcm

    async def _synthesize_safely(self, text: str) -> bytes:
        try:
            return await self._tts.synthesize(text)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TTS failed for %r", text)
            return b""

    async def _stream_pcm(self, epoch: int, pcm: bytes) -> None:
        for offset in range(0, len(pcm), TTS_FRAME_BYTES):
            if self._epoch != epoch:
                return
            chunk = pcm[offset : offset + TTS_FRAME_BYTES]
            if not chunk:
                continue
            await self._send_bytes(encode_audio_frame(epoch=epoch, pcm=chunk))
            duration_s = len(chunk) / (TTS_SAMPLE_RATE * TTS_SAMPLE_WIDTH_BYTES)
            await asyncio.sleep(duration_s)

    async def _stop_speaking(self) -> None:
        old_epoch = self._epoch
        self._epoch += 1
        self._speech_texts.clear()
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tts_task
        self._tts_task = None
        await self._send(SpeakStop(epoch=old_epoch, flush=True))

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

    async def _wait_until_ready(self) -> None:
        if self._ready.is_set():
            return
        self._raise_if_stopped()

        ready_wait = asyncio.create_task(self._ready.wait())
        stopped_wait = asyncio.create_task(self._stopped.wait())
        try:
            await asyncio.wait(
                {ready_wait, stopped_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (ready_wait, stopped_wait):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                ready_wait,
                stopped_wait,
                return_exceptions=True,
            )

        if not self._ready.is_set():
            self._raise_if_stopped()

    def _raise_if_stopped(self) -> None:
        if not self._stopped.is_set():
            return
        error = RuntimeError("orchestrator is not running")
        if self._failure is not None:
            raise error from self._failure
        raise error

    def _fail_pending_dispatches(self) -> None:
        while True:
            try:
                _event, future = self._events.get_nowait()
            except asyncio.QueueEmpty:
                return
            if future is not None and not future.done():
                future.set_exception(RuntimeError("orchestrator stopped"))

    async def _shutdown(self) -> None:
        tasks = {
            task
            for task in (self._tts_task, self._wait_timer, *self._side_tasks)
            if task is not None and not task.done()
        }
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._tts_task = None
        self._wait_timer = None
        self._side_tasks.clear()

        close = getattr(self._responder, "close", None)
        if callable(close):
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("responder close failed")


class ParrotResponder:
    """M2 responder: echoes the user's words back as if an agent replied."""

    def __init__(self, emit: Callable[[sm.Event], None]) -> None:
        self._emit = emit

    async def send(self, text: str) -> None:
        self._emit(sm.AgentSpeakable(text=text, message_id=0))
        self._emit(sm.TurnSettled())

    async def reset(self, chat_key: str) -> None:
        return None

    async def close(self) -> None:
        return None
