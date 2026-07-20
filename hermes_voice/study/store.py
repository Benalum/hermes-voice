"""SQLite storage for Hermes Study decks, cards, media, and sessions."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

CardSection = Literal["question", "answer", "notes"]
Outcome = Literal["correct", "wrong", "skipped"]
_SECTIONS = {"question", "answer", "notes"}
_OUTCOMES = {"correct", "wrong", "skipped"}
_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class StudyNotFoundError(LookupError):
    pass


class StudyConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StudyPaths:
    root: Path
    database: Path
    media: Path

    @classmethod
    def from_env(cls) -> StudyPaths:
        configured = os.environ.get("HV_STUDY_DIR")
        root = (
            Path(configured).expanduser() if configured else Path.home() / ".hermes-voice" / "study"
        )
        return cls(root=root, database=root / "study.sqlite3", media=root / "media")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StudyStore:
    def __init__(self, paths: StudyPaths | None = None) -> None:
        self.paths = paths or StudyPaths.from_env()
        self.paths.root.mkdir(parents=True, exist_ok=True)
        self.paths.media.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.paths.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS decks(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL COLLATE NOCASE UNIQUE,
              description TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cards(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
              question TEXT NOT NULL,
              answer TEXT NOT NULL,
              notes TEXT NOT NULL DEFAULT '',
              position INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS cards_deck_idx ON cards(deck_id, position, id);
            CREATE TABLE IF NOT EXISTS media_assets(
              id TEXT PRIMARY KEY,
              sha256 TEXT NOT NULL UNIQUE,
              mime_type TEXT NOT NULL,
              original_filename TEXT NOT NULL,
              storage_name TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS card_media(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
              media_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
              section TEXT NOT NULL CHECK(section IN ('question','answer','notes')),
              position INTEGER NOT NULL DEFAULT 0,
              UNIQUE(card_id, media_id, section)
            );
            CREATE TABLE IF NOT EXISTS study_sessions(
              id TEXT PRIMARY KEY,
              deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
              mode TEXT NOT NULL,
              status TEXT NOT NULL CHECK(status IN ('active','finished')),
              card_order_json TEXT NOT NULL,
              current_index INTEGER NOT NULL DEFAULT 0,
              answer_revealed INTEGER NOT NULL DEFAULT 0,
              started_at TEXT NOT NULL,
              ended_at TEXT
            );
            CREATE TABLE IF NOT EXISTS study_attempts(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
              card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
              outcome TEXT NOT NULL CHECK(outcome IN ('correct','wrong','skipped')),
              reviewed_at TEXT NOT NULL
            );
            """)

    def list_decks(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
              SELECT d.*, COUNT(DISTINCT c.id) card_count, COUNT(a.id) attempts,
                SUM(a.outcome='correct') correct, SUM(a.outcome='wrong') wrong,
                SUM(a.outcome='skipped') skipped
              FROM decks d LEFT JOIN cards c ON c.deck_id=d.id
              LEFT JOIN study_attempts a ON a.card_id=c.id
              GROUP BY d.id ORDER BY d.name COLLATE NOCASE
            """).fetchall()
        return [self._deck_payload(row) for row in rows]

    def get_deck(self, deck_id: int) -> dict[str, Any]:
        for deck in self.list_decks():
            if deck["id"] == deck_id:
                return deck
        raise StudyNotFoundError("deck not found")

    def find_deck(self, name: str) -> dict[str, Any] | None:
        target = _deck_name(name).casefold()
        decks = self.list_decks()
        exact = [deck for deck in decks if str(deck["name"]).casefold() == target]
        if exact:
            return exact[0]
        matches = [
            deck
            for deck in decks
            if target in str(deck["name"]).casefold() or str(deck["name"]).casefold() in target
        ]
        return matches[0] if len(matches) == 1 else None

    def create_deck(self, name: str, description: str = "") -> dict[str, Any]:
        now = _now()
        try:
            with self._lock, self._connect() as db:
                cursor = db.execute(
                    "INSERT INTO decks(name,description,created_at,updated_at) VALUES(?,?,?,?)",
                    (_deck_name(name), description.strip(), now, now),
                )
                deck_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise StudyConflictError("a deck with that name already exists") from exc
        return self.get_deck(deck_id)

    def update_deck(
        self, deck_id: int, *, name: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        current = self.get_deck(deck_id)
        try:
            with self._lock, self._connect() as db:
                db.execute(
                    "UPDATE decks SET name=?, description=?, updated_at=? WHERE id=?",
                    (
                        _deck_name(name) if name is not None else current["name"],
                        description.strip() if description is not None else current["description"],
                        _now(),
                        deck_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise StudyConflictError("a deck with that name already exists") from exc
        return self.get_deck(deck_id)

    def delete_deck(self, deck_id: int) -> None:
        self.get_deck(deck_id)
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM decks WHERE id=?", (deck_id,))
        self._delete_orphans()

    def list_cards(self, deck_id: int) -> list[dict[str, Any]]:
        self.get_deck(deck_id)
        with self._connect() as db:
            rows = db.execute(
                """
              SELECT c.*, COUNT(a.id) attempts, SUM(a.outcome='correct') correct,
                SUM(a.outcome='wrong') wrong, SUM(a.outcome='skipped') skipped
              FROM cards c LEFT JOIN study_attempts a ON a.card_id=c.id
              WHERE c.deck_id=? GROUP BY c.id ORDER BY c.position,c.id
            """,
                (deck_id,),
            ).fetchall()
        return [self._card_payload(row) for row in rows]

    def get_card(self, card_id: int) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                """
              SELECT c.*, COUNT(a.id) attempts, SUM(a.outcome='correct') correct,
                SUM(a.outcome='wrong') wrong, SUM(a.outcome='skipped') skipped
              FROM cards c LEFT JOIN study_attempts a ON a.card_id=c.id
              WHERE c.id=? GROUP BY c.id
            """,
                (card_id,),
            ).fetchone()
        if row is None:
            raise StudyNotFoundError("card not found")
        return self._card_payload(row)

    def create_card(
        self, deck_id: int, *, question: str, answer: str, notes: str = ""
    ) -> dict[str, Any]:
        self.get_deck(deck_id)
        question, answer = question.strip(), answer.strip()
        if not question or not answer:
            raise ValueError("question and answer are required")
        now = _now()
        with self._lock, self._connect() as db:
            position = int(
                db.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM cards WHERE deck_id=?", (deck_id,)
                ).fetchone()[0]
            )
            cursor = db.execute(
                "INSERT INTO cards(deck_id,question,answer,notes,position,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (deck_id, question, answer, notes.strip(), position, now, now),
            )
            card_id = int(cursor.lastrowid)
        return self.get_card(card_id)

    def update_card(
        self,
        card_id: int,
        *,
        question: str | None = None,
        answer: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_card(card_id)
        next_question = question.strip() if question is not None else current["question"]
        next_answer = answer.strip() if answer is not None else current["answer"]
        if not next_question or not next_answer:
            raise ValueError("question and answer are required")
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE cards SET question=?,answer=?,notes=?,updated_at=? WHERE id=?",
                (
                    next_question,
                    next_answer,
                    notes.strip() if notes is not None else current["notes"],
                    _now(),
                    card_id,
                ),
            )
        return self.get_card(card_id)

    def delete_card(self, card_id: int) -> None:
        self.get_card(card_id)
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM cards WHERE id=?", (card_id,))
        self._delete_orphans()

    def add_card_media(
        self, card_id: int, *, section: CardSection, filename: str, mime_type: str, data_base64: str
    ) -> dict[str, Any]:
        self.get_card(card_id)
        if section not in _SECTIONS or mime_type not in _IMAGE_TYPES:
            raise ValueError("only JPEG, PNG, and WebP card images are supported")
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception as exc:
            raise ValueError("invalid base64 image data") from exc
        if not raw or len(raw) > _MAX_IMAGE_BYTES:
            raise ValueError("image must be between 1 byte and 10 MB")
        _validate_image(raw, mime_type)
        digest = hashlib.sha256(raw).hexdigest()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM media_assets WHERE sha256=?", (digest,)).fetchone()
            if row is None:
                media_id = uuid.uuid4().hex
                storage_name = media_id + _IMAGE_TYPES[mime_type]
                (self.paths.media / storage_name).write_bytes(raw)
                db.execute(
                    "INSERT INTO media_assets VALUES(?,?,?,?,?,?,?)",
                    (
                        media_id,
                        digest,
                        mime_type,
                        Path(filename).name,
                        storage_name,
                        len(raw),
                        _now(),
                    ),
                )
            else:
                media_id = str(row["id"])
            position = int(
                db.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM card_media WHERE card_id=? AND section=?",
                    (card_id, section),
                ).fetchone()[0]
            )
            try:
                db.execute(
                    "INSERT INTO card_media(card_id,media_id,section,position) VALUES(?,?,?,?)",
                    (card_id, media_id, section, position),
                )
            except sqlite3.IntegrityError as exc:
                raise StudyConflictError("that image is already attached to this section") from exc
        return self.get_media(media_id)

    def remove_card_media(self, card_id: int, media_id: str, section: CardSection) -> None:
        self.get_card(card_id)
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "DELETE FROM card_media WHERE card_id=? AND media_id=? AND section=?",
                (card_id, media_id, section),
            )
            if cursor.rowcount == 0:
                raise StudyNotFoundError("card image not found")
        self._delete_orphans()

    def get_media(self, media_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM media_assets WHERE id=?", (media_id,)).fetchone()
        if row is None:
            raise StudyNotFoundError("media not found")
        return {
            "id": str(row["id"]),
            "sha256": str(row["sha256"]),
            "mime_type": str(row["mime_type"]),
            "original_filename": str(row["original_filename"]),
            "size_bytes": int(row["size_bytes"]),
            "path": self.paths.media / str(row["storage_name"]),
            "url": f"/api/study/media/{row['id']}",
        }

    def start_session(
        self, deck_id: int, *, mode: str = "shuffled", limit: int | None = None
    ) -> dict[str, Any]:
        if mode not in {"ordered", "shuffled"}:
            raise ValueError("mode must be ordered or shuffled")
        cards = self.list_cards(deck_id)
        if not cards:
            raise StudyConflictError("that deck does not have any cards")
        order = [int(card["id"]) for card in cards]
        if mode == "shuffled":
            random.SystemRandom().shuffle(order)
        if limit is not None:
            order = order[:limit]
        session_id = uuid.uuid4().hex
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE study_sessions SET status='finished', ended_at=COALESCE(ended_at,?) WHERE status='active'",
                (_now(),),
            )
            db.execute(
                "INSERT INTO study_sessions(id,deck_id,mode,status,card_order_json,started_at) VALUES(?,?,?,'active',?,?)",
                (session_id, deck_id, mode, json.dumps(order), _now()),
            )
        return self.get_session(session_id)

    def start_session_by_name(
        self, name: str, *, mode: str = "shuffled", limit: int | None = None
    ) -> dict[str, Any]:
        deck = self.find_deck(name)
        if deck is None:
            raise StudyNotFoundError("I could not find that deck")
        return self.start_session(int(deck["id"]), mode=mode, limit=limit)

    def current_session(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id FROM study_sessions WHERE status='active' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return None if row is None else self.get_session(str(row["id"]))

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM study_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise StudyNotFoundError("study session not found")
        order = [int(item) for item in json.loads(str(row["card_order_json"]))]
        index = int(row["current_index"])
        counts = self._session_counts(session_id)
        payload: dict[str, Any] = {
            "id": str(row["id"]),
            "deck_id": int(row["deck_id"]),
            "deck": self.get_deck(int(row["deck_id"])),
            "mode": str(row["mode"]),
            "status": str(row["status"]),
            "started_at": str(row["started_at"]),
            "ended_at": row["ended_at"],
            "answer_revealed": bool(row["answer_revealed"]),
            "progress": {
                "current": min(index + 1, len(order)) if order else 0,
                "completed": min(index, len(order)),
                "total": len(order),
                **counts,
            },
            "card": None,
        }
        if payload["status"] == "active" and index < len(order):
            payload["card"] = self.get_card(order[index])
        return payload

    def reveal_answer(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session["status"] != "active" or session["card"] is None:
            raise StudyConflictError("the study session is finished")
        with self._lock, self._connect() as db:
            db.execute("UPDATE study_sessions SET answer_revealed=1 WHERE id=?", (session_id,))
        return self.get_session(session_id)

    def grade(self, session_id: str, outcome: Outcome) -> dict[str, Any]:
        if outcome not in _OUTCOMES:
            raise ValueError("outcome must be correct, wrong, or skipped")
        session = self.get_session(session_id)
        card = session["card"]
        if session["status"] != "active" or card is None:
            raise StudyConflictError("the study session is finished")
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT current_index,card_order_json FROM study_sessions WHERE id=?", (session_id,)
            ).fetchone()
            order = json.loads(str(row["card_order_json"]))
            next_index = int(row["current_index"]) + 1
            db.execute(
                "INSERT INTO study_attempts(session_id,card_id,outcome,reviewed_at) VALUES(?,?,?,?)",
                (session_id, int(card["id"]), outcome, _now()),
            )
            if next_index >= len(order):
                db.execute(
                    "UPDATE study_sessions SET current_index=?,answer_revealed=0,status='finished',ended_at=? WHERE id=?",
                    (next_index, _now(), session_id),
                )
            else:
                db.execute(
                    "UPDATE study_sessions SET current_index=?,answer_revealed=0 WHERE id=?",
                    (next_index, session_id),
                )
        return self.get_session(session_id)

    def finish_session(self, session_id: str) -> dict[str, Any]:
        self.get_session(session_id)
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE study_sessions SET status='finished',ended_at=COALESCE(ended_at,?) WHERE id=?",
                (_now(), session_id),
            )
        return self.get_session(session_id)

    def _session_counts(self, session_id: str) -> dict[str, int]:
        with self._connect() as db:
            row = db.execute(
                "SELECT SUM(outcome='correct') correct,SUM(outcome='wrong') wrong,SUM(outcome='skipped') skipped FROM study_attempts WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("correct", "wrong", "skipped")}

    def _deck_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        correct, wrong = int(row["correct"] or 0), int(row["wrong"] or 0)
        return {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "description": str(row["description"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "card_count": int(row["card_count"] or 0),
            "stats": {
                "attempts": int(row["attempts"] or 0),
                "correct": correct,
                "wrong": wrong,
                "skipped": int(row["skipped"] or 0),
                "accuracy": round(correct / (correct + wrong), 4) if correct + wrong else None,
            },
        }

    def _card_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        correct, wrong = int(row["correct"] or 0), int(row["wrong"] or 0)
        return {
            "id": int(row["id"]),
            "deck_id": int(row["deck_id"]),
            "question": str(row["question"]),
            "answer": str(row["answer"]),
            "notes": str(row["notes"]),
            "position": int(row["position"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "media": self._card_media(int(row["id"])),
            "stats": {
                "attempts": int(row["attempts"] or 0),
                "correct": correct,
                "wrong": wrong,
                "skipped": int(row["skipped"] or 0),
                "accuracy": round(correct / (correct + wrong), 4) if correct + wrong else None,
            },
        }

    def _card_media(self, card_id: int) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT cm.section,cm.position,m.* FROM card_media cm JOIN media_assets m ON m.id=cm.media_id WHERE cm.card_id=? ORDER BY cm.section,cm.position,cm.id",
                (card_id,),
            ).fetchall()
        result: dict[str, list[dict[str, Any]]] = {"question": [], "answer": [], "notes": []}
        for row in rows:
            result[str(row["section"])].append(
                {
                    "id": str(row["id"]),
                    "mime_type": str(row["mime_type"]),
                    "filename": str(row["original_filename"]),
                    "size_bytes": int(row["size_bytes"]),
                    "position": int(row["position"]),
                    "url": f"/api/study/media/{row['id']}",
                }
            )
        return result

    def _delete_orphans(self) -> None:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT m.id,m.storage_name FROM media_assets m LEFT JOIN card_media cm ON cm.media_id=m.id WHERE cm.id IS NULL"
            ).fetchall()
            for row in rows:
                db.execute("DELETE FROM media_assets WHERE id=?", (row["id"],))
                (self.paths.media / str(row["storage_name"])).unlink(missing_ok=True)


def _deck_name(name: str) -> str:
    value = re.sub(r"\s+", " ", name).strip()
    value = re.sub(r"\s+deck$", "", value, flags=re.IGNORECASE).strip()
    if not value:
        raise ValueError("deck name is required")
    if len(value) > 120:
        raise ValueError("deck name must be 120 characters or fewer")
    return value


def _validate_image(raw: bytes, mime_type: str) -> None:
    valid = (
        (mime_type == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"))
        or (mime_type == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
        or (
            mime_type == "image/webp"
            and len(raw) >= 12
            and raw[:4] == b"RIFF"
            and raw[8:12] == b"WEBP"
        )
    )
    if not valid:
        raise ValueError("image contents do not match the declared MIME type")
