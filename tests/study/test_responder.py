from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hermes_voice.kit import session as sm
from hermes_voice.study.responder import StudyResponder
from hermes_voice.study.store import StudyPaths, StudyStore


class Delegate:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)

    async def reset(self, chat_key: str) -> None:
        return None

    async def close(self) -> None:
        return None


def _store(tmp_path: Path) -> StudyStore:
    root = tmp_path / "study"
    return StudyStore(
        StudyPaths(
            root=root,
            database=root / "study.sqlite3",
            media=root / "media",
        )
    )


async def _wait_for_speakable(events: list[sm.Event], *, count: int = 1) -> list[sm.AgentSpeakable]:
    for _ in range(100):
        speakable = [event for event in events if isinstance(event, sm.AgentSpeakable)]
        if len(speakable) >= count:
            return speakable
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for a Study voice announcement")


@pytest.mark.asyncio
async def test_voice_study_commands_stay_local(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck = store.create_deck("MCAT Biology")
    store.create_card(
        deck["id"], question="What organelle produces ATP?", answer="The mitochondrion."
    )
    events: list[sm.Event] = []
    delegate = Delegate()
    responder = StudyResponder(store=store, delegate=delegate, emit=events.append)

    await responder.send("Study my MCAT Biology deck")
    assert delegate.sent == []
    assert isinstance(events[0], sm.AgentSpeakable)
    assert "Question:" in events[0].text

    events.clear()
    await responder.send("show answer")
    assert "mitochondrion" in events[0].text.casefold()

    events.clear()
    await responder.send("correct")
    assert "reviewed 1 cards" in events[0].text.casefold()


@pytest.mark.asyncio
async def test_non_study_text_is_forwarded(tmp_path: Path) -> None:
    store = _store(tmp_path)
    events: list[sm.Event] = []
    delegate = Delegate()
    responder = StudyResponder(store=store, delegate=delegate, emit=events.append)

    await responder.send("What is the weather tomorrow?")
    assert delegate.sent == ["What is the weather tomorrow?"]
    assert events == []


@pytest.mark.asyncio
async def test_active_session_forwards_card_context_to_agent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck = store.create_deck("MCAT Biology")
    store.create_card(
        deck["id"],
        question="What organelle produces ATP?",
        answer="The mitochondrion.",
        notes="Oxidative phosphorylation occurs across the inner mitochondrial membrane.",
    )
    store.start_session(deck["id"], mode="ordered")
    events: list[sm.Event] = []
    delegate = Delegate()
    responder = StudyResponder(store=store, delegate=delegate, emit=events.append)

    await responder.send("It is made in the mitochondria.")

    assert events == []
    assert len(delegate.sent) == 1
    prompt = delegate.sent[0]
    assert "[HERMES STUDY CONTEXT]" in prompt
    assert "Deck: MCAT Biology" in prompt
    assert "Question: What organelle produces ATP?" in prompt
    assert "Expected answer: The mitochondrion." in prompt
    assert "Learner said: It is made in the mitochondria." in prompt


@pytest.mark.asyncio
async def test_browser_session_changes_are_announced_to_voice(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck = store.create_deck("MCAT Biology")
    first = store.create_card(
        deck["id"], question="First question?", answer="First answer."
    )
    second = store.create_card(
        deck["id"], question="Second question?", answer="Second answer."
    )
    events: list[sm.Event] = []
    delegate = Delegate()
    responder = StudyResponder(
        store=store,
        delegate=delegate,
        emit=events.append,
        watch_sessions=True,
        poll_interval_s=0.01,
    )

    try:
        session = store.start_session(deck["id"], mode="ordered")
        speakable = await _wait_for_speakable(events)
        assert str(first["question"]) in speakable[-1].text

        events.clear()
        store.reveal_answer(str(session["id"]))
        speakable = await _wait_for_speakable(events)
        assert str(first["answer"]) in speakable[-1].text

        events.clear()
        store.grade(str(session["id"]), "correct")
        speakable = await _wait_for_speakable(events)
        assert str(second["question"]) in speakable[-1].text
    finally:
        await responder.close()
