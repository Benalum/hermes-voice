"""Attach trusted, package-owned MCAT reference diagrams to starter cards."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from hermes_voice.study.store import StudyStore, _now

_MEDIA_DIR = Path(__file__).resolve().parent / "media"
_ASSETS = (
    (
        "MCAT Biology: Cells, Genetics & Organ Systems",
        "How do simple diffusion, facilitated diffusion, and active transport differ?",
        "question",
        "membrane_transport.svg",
    ),
    (
        "MCAT Biochemistry: Amino Acids, Enzymes & Metabolism",
        "How can you predict whether an ionizable group is mostly protonated or deprotonated?",
        "notes",
        "amino_acid_zwitterion.svg",
    ),
    (
        "MCAT General & Organic Chemistry",
        "How does normal-phase silica chromatography separate compounds?",
        "answer",
        "chromatography_normal_phase.svg",
    ),
    (
        "MCAT Physics: Mechanics, Fluids, Circuits & Optics",
        "How do equivalent resistance rules differ for series and parallel resistors?",
        "answer",
        "circuits_series_parallel.svg",
    ),
    (
        "MCAT Physics: Mechanics, Fluids, Circuits & Optics",
        "What image does a converging lens form when the object is beyond the focal point?",
        "answer",
        "converging_lens.svg",
    ),
    (
        "MCAT Psychology & Sociology",
        "What is the key difference between classical and operant conditioning?",
        "answer",
        "conditioning_comparison.svg",
    ),
    (
        "MCAT CARS: Passage Reasoning",
        "What is the purpose of a brief passage map?",
        "notes",
        "cars_passage_map.svg",
    ),
)


def install_mcat_media(store: StudyStore) -> dict[str, int]:
    """Install trusted SVGs without exposing SVG through the user upload API."""
    attached = 0
    skipped = 0
    missing = 0

    for deck_name, question, section, filename in _ASSETS:
        deck = store.find_deck(deck_name)
        if deck is None:
            missing += 1
            continue
        card = next(
            (
                item
                for item in store.list_cards(int(deck["id"]))
                if str(item["question"]) == question
            ),
            None,
        )
        if card is None:
            missing += 1
            continue

        raw = (_MEDIA_DIR / filename).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        card_id = int(card["id"])

        with store._lock, store._connect() as db:
            media = db.execute(
                "SELECT id,storage_name FROM media_assets WHERE sha256=?",
                (digest,),
            ).fetchone()
            if media is None:
                media_id = uuid.uuid4().hex
                storage_name = f"{media_id}.svg"
                (store.paths.media / storage_name).write_bytes(raw)
                db.execute(
                    "INSERT INTO media_assets VALUES(?,?,?,?,?,?,?)",
                    (
                        media_id,
                        digest,
                        "image/svg+xml",
                        filename,
                        storage_name,
                        len(raw),
                        _now(),
                    ),
                )
            else:
                media_id = str(media["id"])

            exists = db.execute(
                "SELECT 1 FROM card_media WHERE card_id=? AND media_id=? AND section=?",
                (card_id, media_id, section),
            ).fetchone()
            if exists is not None:
                skipped += 1
                continue
            position = int(
                db.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM card_media "
                    "WHERE card_id=? AND section=?",
                    (card_id, section),
                ).fetchone()[0]
            )
            db.execute(
                "INSERT INTO card_media(card_id,media_id,section,position) "
                "VALUES(?,?,?,?)",
                (card_id, media_id, section, position),
            )
            attached += 1

    return {"attached": attached, "skipped": skipped, "missing": missing}
