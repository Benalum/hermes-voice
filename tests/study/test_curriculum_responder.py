from __future__ import annotations

from pathlib import Path

import pytest

from hermes_voice.kit import session as sm
from hermes_voice.study.curriculum import foundation_curriculum_skeleton
from hermes_voice.study.curriculum_responder import CurriculumStudyResponder
from hermes_voice.study.curriculum_store import CurriculumStore
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


def _responder(
    tmp_path: Path,
) -> tuple[StudyStore, CurriculumStore, CurriculumStudyResponder, list[sm.Event]]:
    root = tmp_path / "study"
    paths = StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media")
    study = StudyStore(paths)
    curricula = CurriculumStore(paths)
    curricula.install_curriculum(foundation_curriculum_skeleton())
    events: list[sm.Event] = []
    responder = CurriculumStudyResponder(
        store=study,
        curriculum_store=curricula,
        delegate=Delegate(),
        emit=events.append,
    )
    return study, curricula, responder, events


@pytest.mark.asyncio
async def test_continue_curriculum_and_rate_good(tmp_path: Path) -> None:
    study, curricula, responder, events = _responder(tmp_path)
    first = foundation_curriculum_skeleton().ordered_decks()[0]
    deck = study.create_deck("Learning")
    card = study.create_card(int(deck["id"]), question="What is recall?", answer="Retrieval")
    curricula.bind_deck(first.key, int(deck["id"]))

    await responder.send("continue curriculum")
    assert "continuing your curriculum" in events[0].text.casefold()

    events.clear()
    await responder.send("good")

    assert "good recorded" in events[0].text.casefold()
    assert curricula.get_review_state(int(card["id"])).rating == "good"
    assert study.current_session() is None


@pytest.mark.parametrize(
    ("command", "outcome"),
    [
        ("mark right", "correct"),
        ("mark it right", "correct"),
        ("mark this right", "correct"),
        ("mark that right", "correct"),
        ("mark correct", "correct"),
        ("mark it correct", "correct"),
        ("skip", "skipped"),
        ("skip card", "skipped"),
        ("skip the card", "skipped"),
        ("skip this card", "skipped"),
        ("skip that card", "skipped"),
        ("skip it", "skipped"),
        ("mark skipped", "skipped"),
        ("next card", "skipped"),
    ],
)
@pytest.mark.asyncio
async def test_natural_grade_commands_stay_local_and_advance(
    tmp_path: Path,
    command: str,
    outcome: str,
) -> None:
    study, _, responder, events = _responder(tmp_path)
    deck = study.create_deck("Learning")
    first = study.create_card(int(deck["id"]), question="First question?", answer="First")
    second = study.create_card(int(deck["id"]), question="Second question?", answer="Second")
    session = study.start_session(int(deck["id"]), mode="ordered")
    assert int(session["card"]["id"]) == int(first["id"])

    delegate = responder._delegate
    await responder.send(command)

    assert isinstance(delegate, Delegate)
    assert delegate.sent == []
    assert isinstance(events[0], sm.AgentSpeakable)
    assert "second question" in events[0].text.casefold()

    current = study.current_session()
    assert current is not None
    assert int(current["card"]["id"]) == int(second["id"])
    assert current["progress"][outcome] == 1
    assert current["progress"]["completed"] == 1


@pytest.mark.asyncio
async def test_curriculum_progress_and_cumulative_review_are_local(tmp_path: Path) -> None:
    study, curricula, responder, events = _responder(tmp_path)
    first = foundation_curriculum_skeleton().ordered_decks()[0]
    deck = study.create_deck("Learning")
    study.create_card(int(deck["id"]), question="Q?", answer="A")
    curricula.bind_deck(first.key, int(deck["id"]))

    await responder.send("curriculum progress")
    assert "curriculum mastery" in events[0].text.casefold()

    events.clear()
    await responder.send("start cumulative review")
    assert "cumulative review" in events[0].text.casefold()
