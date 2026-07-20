from __future__ import annotations

from pathlib import Path

from hermes_voice.study.starter_packs import install_mcat_foundations
from hermes_voice.study.store import StudyPaths, StudyStore


def make_store(tmp_path: Path) -> StudyStore:
    root = tmp_path / "study"
    return StudyStore(
        StudyPaths(
            root=root,
            database=root / "study.sqlite3",
            media=root / "media",
        )
    )


def test_mcat_pack_is_populated_and_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    first = install_mcat_foundations(store)
    assert first == {
        "decks_created": 6,
        "cards_created": 30,
        "cards_skipped": 0,
    }
    assert len(store.list_decks()) == 6
    assert sum(deck["card_count"] for deck in store.list_decks()) == 30

    second = install_mcat_foundations(store)
    assert second == {
        "decks_created": 0,
        "cards_created": 0,
        "cards_skipped": 30,
    }
    assert sum(deck["card_count"] for deck in store.list_decks()) == 30
