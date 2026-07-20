from __future__ import annotations

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


@pytest.mark.asyncio
async def test_voice_study_commands_stay_local(tmp_path: Path) -> None:
    root = tmp_path / "study"
    store = StudyStore(StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media"))
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
    root = tmp_path / "study"
    store = StudyStore(StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media"))
    events: list[sm.Event] = []
    delegate = Delegate()
    responder = StudyResponder(store=store, delegate=delegate, emit=events.append)

    await responder.send("What is the weather tomorrow?")
    assert delegate.sent == ["What is the weather tomorrow?"]
    assert events == []
