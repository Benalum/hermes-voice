from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hermes_voice.study.curriculum import foundation_curriculum_skeleton
from hermes_voice.study.curriculum_store import CurriculumStore, review_state_payload
from hermes_voice.study.store import StudyNotFoundError, StudyPaths, StudyStore


def _stores(tmp_path: Path) -> tuple[StudyStore, CurriculumStore]:
    paths = StudyPaths(
        root=tmp_path / "study",
        database=tmp_path / "study" / "study.sqlite3",
        media=tmp_path / "study" / "media",
    )
    study = StudyStore(paths)
    return study, CurriculumStore(paths)


def test_install_and_reload_foundation_curriculum(tmp_path: Path) -> None:
    _study, curricula = _stores(tmp_path)
    source = foundation_curriculum_skeleton()

    installed = curricula.install_curriculum(source)
    reloaded = curricula.get_curriculum(source.key)

    assert installed == {"courses": 22, "decks": 22}
    assert reloaded == source
    assert curricula.list_curricula() == [
        {
            "key": source.key,
            "name": source.name,
            "version": source.version,
            "description": source.description,
            "created_at": curricula.list_curricula()[0]["created_at"],
            "updated_at": curricula.list_curricula()[0]["updated_at"],
            "course_count": 22,
            "deck_count": 22,
            "bound_deck_count": 0,
        }
    ]


def test_install_is_idempotent_and_preserves_bound_deck(tmp_path: Path) -> None:
    study, curricula = _stores(tmp_path)
    curriculum = foundation_curriculum_skeleton()
    curricula.install_curriculum(curriculum)
    deck = study.create_deck("Learning Foundations")
    curriculum_deck = curriculum.ordered_decks()[0]

    bound = curricula.bind_deck(curriculum_deck.key, int(deck["id"]))
    curricula.install_curriculum(curriculum)
    rebound = curricula.get_curriculum_deck(curriculum_deck.key)

    assert bound["deck_id"] == deck["id"]
    assert rebound["deck_id"] == deck["id"]
    assert curricula.list_curricula()[0]["bound_deck_count"] == 1


def test_bind_deck_rejects_missing_records(tmp_path: Path) -> None:
    study, curricula = _stores(tmp_path)
    curriculum = foundation_curriculum_skeleton()
    curricula.install_curriculum(curriculum)
    deck = study.create_deck("Foundations")

    with pytest.raises(StudyNotFoundError, match="curriculum deck"):
        curricula.bind_deck("missing", int(deck["id"]))
    with pytest.raises(StudyNotFoundError, match="deck not found"):
        curricula.bind_deck(curriculum.ordered_decks()[0].key, 9999)


def test_review_schedule_progresses_and_tracks_lapses(tmp_path: Path) -> None:
    study, curricula = _stores(tmp_path)
    deck = study.create_deck("Biology")
    card = study.create_card(
        int(deck["id"]), question="What is ATP?", answer="The cell's energy currency."
    )
    card_id = int(card["id"])
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)

    initial = curricula.get_review_state(card_id)
    good = curricula.record_review(card_id, "good", reviewed_at=now)
    easy = curricula.record_review(card_id, "easy", reviewed_at=now + timedelta(days=1))
    again = curricula.record_review(card_id, "again", reviewed_at=now + timedelta(days=2))

    assert initial.review_count == 0
    assert good.review_count == 1
    assert good.due_at == (now + timedelta(days=1)).isoformat()
    assert easy.stability > good.stability
    assert again.lapse_count == 1
    assert again.due_at == (now + timedelta(days=2, hours=0.96)).isoformat()
    assert review_state_payload(again)["rating"] == "again"


def test_skipped_review_does_not_increment_review_count(tmp_path: Path) -> None:
    study, curricula = _stores(tmp_path)
    deck = study.create_deck("Chemistry")
    card = study.create_card(int(deck["id"]), question="What is pH?", answer="Negative log H+.")

    state = curricula.record_review(int(card["id"]), "skipped")

    assert state.rating == "skipped"
    assert state.review_count == 0
    assert state.due_at is None


def test_due_cards_are_ordered_and_limited(tmp_path: Path) -> None:
    study, curricula = _stores(tmp_path)
    deck = study.create_deck("Physics")
    cards = [
        study.create_card(int(deck["id"]), question=f"Q{index}", answer=f"A{index}")
        for index in range(3)
    ]
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    for card in cards:
        curricula.record_review(int(card["id"]), "again", reviewed_at=now)

    due = curricula.due_card_ids(at=now + timedelta(hours=1), limit=2)

    assert due == tuple(int(card["id"]) for card in cards[:2])
    with pytest.raises(ValueError, match="positive"):
        curricula.due_card_ids(limit=0)


def test_deleting_card_removes_review_state(tmp_path: Path) -> None:
    study, curricula = _stores(tmp_path)
    deck = study.create_deck("Psychology")
    card = study.create_card(int(deck["id"]), question="What is memory?", answer="Stored information.")
    card_id = int(card["id"])
    curricula.record_review(card_id, "good")

    study.delete_card(card_id)

    with pytest.raises(StudyNotFoundError, match="card not found"):
        curricula.get_review_state(card_id)
