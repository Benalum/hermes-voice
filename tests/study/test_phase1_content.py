from __future__ import annotations

from hermes_voice.study.curriculum import foundation_curriculum_skeleton
from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.phase1_content import COURSES, install_phase1_content
from hermes_voice.study.store import StudyPaths, StudyStore


def test_phase1_content_pack_is_complete_bound_visual_and_idempotent(tmp_path) -> None:
    paths = StudyPaths(
        root=tmp_path / "study",
        database=tmp_path / "study" / "study.sqlite3",
        media=tmp_path / "study" / "media",
    )
    store = StudyStore(paths)
    curriculum_store = CurriculumStore(paths)
    curriculum_store.install_curriculum(foundation_curriculum_skeleton())

    first = install_phase1_content(store, curriculum_store)

    assert first["courses"] == 22
    assert first["decks_created"] == 22
    assert first["cards_created"] == 660
    assert first["media_attached"] == 44
    assert first["bindings"] == 22
    assert first["total_cards"] == 660

    decks = store.list_decks()
    assert len(decks) == 22
    assert {deck["name"] for deck in decks} == {name for _, name, _ in COURSES}
    assert min(int(deck["card_count"]) for deck in decks) == 30
    assert sum(int(deck["card_count"]) for deck in decks) == 660

    for deck in decks:
        cards = store.list_cards(int(deck["id"]))
        questions = [str(card["question"]).strip().casefold() for card in cards]
        assert len(questions) == len(set(questions))
        media_count = sum(
            len(card["media"]["question"])
            + len(card["media"]["answer"])
            + len(card["media"]["notes"])
            for card in cards
        )
        assert media_count == 2

    curriculum = curriculum_store.list_curricula()[0]
    assert int(curriculum["course_count"]) == 22
    assert int(curriculum["deck_count"]) == 22
    assert int(curriculum["bound_deck_count"]) == 22

    second = install_phase1_content(store, curriculum_store)
    assert second["decks_created"] == 0
    assert second["cards_created"] == 0
    assert second["cards_skipped"] == 660
    assert second["media_attached"] == 0
    assert second["media_skipped"] == 44
    assert second["total_cards"] == 660
