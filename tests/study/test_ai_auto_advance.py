from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from hermes_voice.kit import session as sm
from hermes_voice.study.install import wrap_responder_factory
from hermes_voice.study.responder import StudyResponder
from hermes_voice.study.store import StudyPaths, StudyStore


class Delegate:
    def __init__(self, emit: Callable[[sm.Event], None] | None = None) -> None:
        self.emit = emit
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)

    async def reset(self, chat_key: str) -> None:
        return None

    async def close(self) -> None:
        return None

    def reply(self, text: str, *, message_id: int = 1) -> None:
        assert self.emit is not None
        self.emit(sm.AgentSpeakable(text=text, message_id=message_id))
        self.emit(sm.TurnSettled())


def _store(tmp_path: Path) -> StudyStore:
    root = tmp_path / "study"
    return StudyStore(
        StudyPaths(
            root=root,
            database=root / "study.sqlite3",
            media=root / "media",
        )
    )


def _deck_with_cards(store: StudyStore, count: int = 5) -> tuple[dict, list[dict]]:
    deck = store.create_deck("Full Flow")
    cards = [
        store.create_card(
            deck["id"],
            question=f"Question {number}?",
            answer=f"Answer {number}.",
            notes=f"Material for card {number}.",
        )
        for number in range(1, count + 1)
    ]
    return deck, cards


def _current_card_id(store: StudyStore) -> int:
    session = store.current_session()
    assert session is not None
    assert session["card"] is not None
    return int(session["card"]["id"])


def _spoken(events: list[sm.Event]) -> list[str]:
    return [event.text for event in events if isinstance(event, sm.AgentSpeakable)]


@pytest.mark.asyncio
async def test_explanation_repeats_card_then_natural_answer_advances(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck, cards = _deck_with_cards(store, count=3)
    store.start_session(deck["id"], mode="ordered")

    events: list[sm.Event] = []
    delegate = Delegate()
    responder = StudyResponder(store=store, delegate=delegate, emit=events.append)

    await responder.send("go over the material")
    assert "ALLOWED FINAL MARKERS" in delegate.sent[-1]
    assert "Learner said: go over the material" in delegate.sent[-1]

    responder.handle_delegate_event(
        sm.AgentSpeakable(
            text=(
                "Mitochondria generate ATP through oxidative phosphorylation.\n"
                "[[HERMES_STUDY_ACTION:repeat_question]]"
            ),
            message_id=10,
        )
    )
    responder.handle_delegate_event(sm.TurnSettled())

    assert _current_card_id(store) == int(cards[0]["id"])
    assert any("Question 1?" in text for text in _spoken(events))
    assert all("HERMES_STUDY_ACTION" not in text for text in _spoken(events))

    events.clear()
    await responder.send("Answer 1.")
    responder.handle_delegate_event(
        sm.AgentSpeakable(
            text=("Correct. That matches the expected answer.\n[[HERMES_STUDY_ACTION:grade_good]]"),
            message_id=11,
        )
    )
    responder.handle_delegate_event(sm.TurnSettled())

    assert _current_card_id(store) == int(cards[1]["id"])
    session = store.current_session()
    assert session is not None
    assert session["progress"]["completed"] == 1
    assert session["progress"]["correct"] == 1
    assert any("Question 2?" in text for text in _spoken(events))

    await responder.close()


@pytest.mark.asyncio
async def test_natural_voice_grade_aliases_advance_and_persist(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck, cards = _deck_with_cards(store, count=5)
    store.start_session(deck["id"], mode="ordered")

    events: list[sm.Event] = []
    responder = StudyResponder(store=store, delegate=Delegate(), emit=events.append)

    await responder.send("skip the question")
    assert _current_card_id(store) == int(cards[1]["id"])

    await responder.send("mark answer right")
    assert _current_card_id(store) == int(cards[2]["id"])

    await responder.send("mark the answer wrong")
    assert _current_card_id(store) == int(cards[3]["id"])

    session = store.current_session()
    assert session is not None
    assert session["progress"]["completed"] == 3
    assert session["progress"]["skipped"] == 1
    assert session["progress"]["correct"] == 1
    assert session["progress"]["wrong"] == 1

    await responder.close()


@pytest.mark.asyncio
async def test_factory_bridge_applies_delegate_action_to_sqlite(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck, cards = _deck_with_cards(store, count=3)
    store.start_session(deck["id"], mode="ordered")

    events: list[sm.Event] = []
    created: list[Delegate] = []

    def make_delegate(emit: Callable[[sm.Event], None]) -> Delegate:
        delegate = Delegate(emit)
        created.append(delegate)
        return delegate

    responder = wrap_responder_factory(store, make_delegate)(events.append)
    await responder.send("Answer 1.")

    assert len(created) == 1
    created[0].reply(
        "Correct.\n[[HERMES_STUDY_ACTION:grade_good]]",
        message_id=20,
    )

    assert _current_card_id(store) == int(cards[1]["id"])
    session = store.current_session()
    assert session is not None
    assert session["progress"]["completed"] == 1
    assert session["progress"]["correct"] == 1
    assert all("HERMES_STUDY_ACTION" not in text for text in _spoken(events))
    assert any("Question 2?" in text for text in _spoken(events))

    await responder.close()


@pytest.mark.asyncio
async def test_unsupported_or_missing_marker_cannot_mutate_study_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    deck, cards = _deck_with_cards(store, count=2)
    store.start_session(deck["id"], mode="ordered")

    events: list[sm.Event] = []
    responder = StudyResponder(store=store, delegate=Delegate(), emit=events.append)

    responder.handle_delegate_event(
        sm.AgentSpeakable(text="Looks correct, but there is no action marker.", message_id=30)
    )
    responder.handle_delegate_event(sm.TurnSettled())
    assert _current_card_id(store) == int(cards[0]["id"])

    responder.handle_delegate_event(
        sm.AgentSpeakable(
            text="Trying an invalid action.\n[[HERMES_STUDY_ACTION:delete_deck]]",
            message_id=31,
        )
    )
    responder.handle_delegate_event(sm.TurnSettled())
    assert _current_card_id(store) == int(cards[0]["id"])

    await responder.close()
