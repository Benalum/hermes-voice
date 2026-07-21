from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hermes_voice.study.curriculum import foundation_curriculum_skeleton
from hermes_voice.study.curriculum_runtime import CurriculumRuntime
from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.store import StudyPaths, StudyStore


def _runtime(tmp_path: Path) -> tuple[StudyStore, CurriculumStore, CurriculumRuntime]:
    root = tmp_path / "study"
    paths = StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media")
    study = StudyStore(paths)
    curricula = CurriculumStore(paths)
    curricula.install_curriculum(foundation_curriculum_skeleton())
    return study, curricula, CurriculumRuntime(study, curricula)


def test_progress_unlocks_next_bound_lesson_after_mastery(tmp_path: Path) -> None:
    study, curricula, runtime = _runtime(tmp_path)
    curriculum = foundation_curriculum_skeleton()
    first, second = curriculum.ordered_decks()[:2]
    first_deck = study.create_deck("First")
    second_deck = study.create_deck("Second")
    first_cards = [
        study.create_card(int(first_deck["id"]), question=f"Q{i}", answer=f"A{i}")
        for i in range(10)
    ]
    study.create_card(int(second_deck["id"]), question="Next?", answer="Yes")
    curricula.bind_deck(first.key, int(first_deck["id"]))
    curricula.bind_deck(second.key, int(second_deck["id"]))

    locked = runtime.progress(curriculum.key)
    assert locked["next_deck"]["key"] == first.key
    assert locked["courses"][1]["decks"][0]["unlocked"] is False

    for card in first_cards[:8]:
        curricula.record_review(int(card["id"]), "good")

    unlocked = runtime.progress(curriculum.key)
    assert unlocked["courses"][0]["decks"][0]["completed"] is True
    assert unlocked["courses"][1]["decks"][0]["unlocked"] is True
    assert unlocked["next_deck"]["key"] == second.key


def test_continue_curriculum_starts_ordered_next_lesson(tmp_path: Path) -> None:
    study, curricula, runtime = _runtime(tmp_path)
    first = foundation_curriculum_skeleton().ordered_decks()[0]
    deck = study.create_deck("Learning")
    card = study.create_card(int(deck["id"]), question="Recall?", answer="Retrieve")
    curricula.bind_deck(first.key, int(deck["id"]))

    session = runtime.continue_curriculum("mcat-medical-foundations-phase-1")

    assert session["mode"] == "ordered"
    assert session["card"]["id"] == card["id"]


def test_cumulative_review_interleaves_unlocked_bound_cards(tmp_path: Path) -> None:
    study, curricula, runtime = _runtime(tmp_path)
    first = foundation_curriculum_skeleton().ordered_decks()[0]
    deck = study.create_deck("Learning")
    cards = [
        study.create_card(int(deck["id"]), question=f"Q{i}", answer=f"A{i}")
        for i in range(4)
    ]
    curricula.bind_deck(first.key, int(deck["id"]))
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    curricula.record_review(int(cards[0]["id"]), "again", reviewed_at=now - timedelta(days=1))
    curricula.record_review(int(cards[1]["id"]), "hard", reviewed_at=now - timedelta(days=2))

    session = runtime.start_cumulative_review(
        "mcat-medical-foundations-phase-1",
        limit=3,
        now=now,
    )

    assert session["mode"] == "cumulative"
    assert session["progress"]["total"] == 3
    assert session["card"]["id"] in {card["id"] for card in cards}
