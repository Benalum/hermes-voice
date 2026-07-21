from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

import pytest

from hermes_voice.kit import session as sm
from hermes_voice.kit.turns import BargeIn, TurnConfig
from hermes_voice.server.immediate_barge import ImmediateBargeInOrchestrator


class FakeVad:
    def probability(self, frame: bytes) -> float:
        return 1.0


class FakeStt:
    async def transcribe(self, pcm: bytes) -> str:
        return "interrupted question"


class FakeTts:
    async def synthesize(self, text: str) -> bytes:
        return b""


class DummyResponder:
    async def send(self, text: str) -> None:
        return None

    async def reset(self, chat_key: str) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeTurns:
    def __init__(self, events: tuple[object, ...]) -> None:
        self.config = TurnConfig()
        self.events = events
        self.speaking_values: list[bool] = []

    def feed(self, pcm: bytes, probability: float, *, speaking: bool) -> tuple[object, ...]:
        self.speaking_values.append(speaking)
        return self.events


def _make_orchestrator(
    send_text: Callable[[str], Awaitable[None]],
) -> ImmediateBargeInOrchestrator:
    def make_responder(_emit: Callable[[sm.Event], None]) -> DummyResponder:
        return DummyResponder()

    return ImmediateBargeInOrchestrator(
        send_text=send_text,
        send_bytes=_discard_bytes,
        vad=FakeVad(),
        stt=FakeStt(),
        tts=FakeTts(),
        make_responder=make_responder,
        initial_chat="agent",
    )


async def _discard_bytes(_payload: bytes) -> None:
    return None


@pytest.mark.asyncio
async def test_unmuted_barge_in_stops_speech_immediately() -> None:
    sent: list[str] = []

    async def send_text(payload: str) -> None:
        sent.append(payload)

    orchestrator = _make_orchestrator(send_text)
    orchestrator._session = sm.Session(
        state=sm.State.SPEAKING,
        turn_open=False,
        chat_key="agent",
    )
    turns = FakeTurns((BargeIn(),))
    orchestrator._turns = cast(Any, turns)

    orchestrator.feed_audio(b"speech frame")

    event, future = orchestrator._events.get_nowait()
    assert future is None
    assert isinstance(event, sm.BargedIn)
    assert orchestrator._pending_barge_in is True
    assert turns.speaking_values == [True]

    await orchestrator._handle(event)

    assert orchestrator._session.state is sm.State.LISTENING
    assert orchestrator._epoch == 2
    assert sent, "the browser must receive stop/state control messages"


@pytest.mark.asyncio
async def test_repeated_barge_detection_emits_one_interrupt() -> None:
    async def send_text(_payload: str) -> None:
        return None

    orchestrator = _make_orchestrator(send_text)
    orchestrator._session = sm.Session(
        state=sm.State.SPEAKING,
        turn_open=False,
        chat_key="agent",
    )
    orchestrator._turns = cast(Any, FakeTurns((BargeIn(),)))

    orchestrator.feed_audio(b"first")
    orchestrator.feed_audio(b"second")

    assert orchestrator._events.qsize() == 1


@pytest.mark.asyncio
async def test_muted_speech_does_not_trigger_immediate_barge_in() -> None:
    async def send_text(_payload: str) -> None:
        return None

    orchestrator = _make_orchestrator(send_text)
    orchestrator._voice_mute.set_muted(True)
    orchestrator._session = sm.Session(
        state=sm.State.SPEAKING,
        turn_open=False,
        chat_key="agent",
    )
    turns = FakeTurns((BargeIn(),))
    orchestrator._turns = cast(Any, turns)

    orchestrator.feed_audio(b"muted speech")

    assert turns.speaking_values == [False]
    assert orchestrator._events.empty()
    assert orchestrator._pending_barge_in is False
