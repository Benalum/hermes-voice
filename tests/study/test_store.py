from __future__ import annotations

import base64
from pathlib import Path

from hermes_voice.study.store import StudyPaths, StudyStore


def make_store(tmp_path: Path) -> StudyStore:
    root = tmp_path / "study"
    return StudyStore(StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media"))


def test_decks_cards_sessions_and_stats(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    deck = store.create_deck("MCAT Biology", "Cells and systems")
    first = store.create_card(
        deck["id"],
        question="What organelle produces most ATP?",
        answer="The mitochondrion.",
        notes="Through oxidative phosphorylation.",
    )
    store.create_card(deck["id"], question="What stores genetic material?", answer="The nucleus.")

    session = store.start_session(deck["id"], mode="ordered")
    assert session["card"]["id"] == first["id"]
    assert session["progress"]["total"] == 2
    assert store.reveal_answer(session["id"])["answer_revealed"] is True

    next_card = store.grade(session["id"], "correct")
    assert next_card["progress"]["correct"] == 1
    assert next_card["status"] == "active"

    finished = store.grade(session["id"], "wrong")
    assert finished["status"] == "finished"
    assert finished["progress"]["correct"] == 1
    assert finished["progress"]["wrong"] == 1
    assert store.get_deck(deck["id"])["stats"]["accuracy"] == 0.5


def test_card_images_are_stored_once_and_associated_by_section(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    deck = store.create_deck("Anatomy")
    card = store.create_card(deck["id"], question="Identify this.", answer="Femur")
    png = b"\x89PNG\r\n\x1a\n" + b"test-payload"
    encoded = base64.b64encode(png).decode()

    media = store.add_card_media(
        card["id"],
        section="question",
        filename="femur.png",
        mime_type="image/png",
        data_base64=encoded,
    )
    updated = store.get_card(card["id"])
    assert updated["media"]["question"][0]["id"] == media["id"]
    assert media["path"].read_bytes() == png

    store.remove_card_media(card["id"], media["id"], "question")
    assert store.get_card(card["id"])["media"]["question"] == []
    assert not media["path"].exists()
