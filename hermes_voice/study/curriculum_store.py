"""SQLite persistence for curricula, progression metadata, and card review state.

The curriculum tables live beside the existing Hermes Study tables but do not alter
or constrain user-created decks. A deck participates in progression only after it
is explicitly bound to a curriculum deck record.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from hermes_voice.study.curriculum import (
    Curriculum,
    CurriculumCourse,
    CurriculumDeck,
    ReviewRating,
)
from hermes_voice.study.store import StudyNotFoundError, StudyPaths


@dataclass(frozen=True, slots=True)
class CardReviewState:
    card_id: int
    rating: ReviewRating | None = None
    stability: float = 0.0
    difficulty: float = 5.0
    due_at: str | None = None
    last_reviewed_at: str | None = None
    review_count: int = 0
    lapse_count: int = 0


class CurriculumStore:
    """Persist curriculum definitions without changing existing Study behavior."""

    def __init__(self, paths: StudyPaths) -> None:
        self.paths = paths
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.paths.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS curricula(
                  key TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  version TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS curriculum_courses(
                  key TEXT PRIMARY KEY,
                  curriculum_key TEXT NOT NULL REFERENCES curricula(key) ON DELETE CASCADE,
                  name TEXT NOT NULL,
                  position INTEGER NOT NULL,
                  completion_mastery REAL NOT NULL,
                  prerequisite_keys_json TEXT NOT NULL DEFAULT '[]',
                  UNIQUE(curriculum_key, position)
                );
                CREATE TABLE IF NOT EXISTS curriculum_decks(
                  key TEXT PRIMARY KEY,
                  course_key TEXT NOT NULL REFERENCES curriculum_courses(key) ON DELETE CASCADE,
                  deck_id INTEGER REFERENCES decks(id) ON DELETE SET NULL,
                  name TEXT NOT NULL,
                  position INTEGER NOT NULL,
                  unlock_mastery REAL NOT NULL,
                  completion_mastery REAL NOT NULL,
                  checkpoint INTEGER NOT NULL DEFAULT 0,
                  UNIQUE(course_key, position),
                  UNIQUE(deck_id)
                );
                CREATE TABLE IF NOT EXISTS deck_prerequisites(
                  deck_key TEXT NOT NULL REFERENCES curriculum_decks(key) ON DELETE CASCADE,
                  prerequisite_key TEXT NOT NULL REFERENCES curriculum_decks(key) ON DELETE CASCADE,
                  PRIMARY KEY(deck_key, prerequisite_key),
                  CHECK(deck_key <> prerequisite_key)
                );
                CREATE TABLE IF NOT EXISTS card_review_state(
                  card_id INTEGER PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
                  rating TEXT CHECK(rating IN ('again','hard','good','easy','skipped')),
                  stability REAL NOT NULL DEFAULT 0,
                  difficulty REAL NOT NULL DEFAULT 5,
                  due_at TEXT,
                  last_reviewed_at TEXT,
                  review_count INTEGER NOT NULL DEFAULT 0,
                  lapse_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS curriculum_courses_order_idx
                  ON curriculum_courses(curriculum_key, position, key);
                CREATE INDEX IF NOT EXISTS curriculum_decks_order_idx
                  ON curriculum_decks(course_key, position, key);
                CREATE INDEX IF NOT EXISTS card_review_due_idx
                  ON card_review_state(due_at, card_id);
                """
            )

    def install_curriculum(self, curriculum: Curriculum) -> dict[str, int]:
        """Install or refresh a curriculum definition idempotently."""
        now = _now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO curricula(key,name,version,description,created_at,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                  name=excluded.name,
                  version=excluded.version,
                  description=excluded.description,
                  updated_at=excluded.updated_at
                """,
                (
                    curriculum.key,
                    curriculum.name,
                    curriculum.version,
                    curriculum.description,
                    now,
                    now,
                ),
            )
            course_keys = {course.key for course in curriculum.courses}
            deck_keys = {deck.key for course in curriculum.courses for deck in course.decks}
            if course_keys:
                placeholders = ",".join("?" for _ in course_keys)
                db.execute(
                    f"DELETE FROM curriculum_courses WHERE curriculum_key=? AND key NOT IN ({placeholders})",
                    (curriculum.key, *sorted(course_keys)),
                )
            for course in curriculum.ordered_courses():
                db.execute(
                    """
                    INSERT INTO curriculum_courses(
                      key,curriculum_key,name,position,completion_mastery,prerequisite_keys_json
                    ) VALUES(?,?,?,?,?,json(?))
                    ON CONFLICT(key) DO UPDATE SET
                      curriculum_key=excluded.curriculum_key,
                      name=excluded.name,
                      position=excluded.position,
                      completion_mastery=excluded.completion_mastery,
                      prerequisite_keys_json=excluded.prerequisite_keys_json
                    """,
                    (
                        course.key,
                        curriculum.key,
                        course.name,
                        course.order,
                        course.completion_mastery,
                        _json_array(course.prerequisite_course_keys),
                    ),
                )
                for deck in sorted(course.decks, key=lambda item: (item.order, item.key)):
                    db.execute(
                        """
                        INSERT INTO curriculum_decks(
                          key,course_key,name,position,unlock_mastery,completion_mastery,checkpoint
                        ) VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(key) DO UPDATE SET
                          course_key=excluded.course_key,
                          name=excluded.name,
                          position=excluded.position,
                          unlock_mastery=excluded.unlock_mastery,
                          completion_mastery=excluded.completion_mastery,
                          checkpoint=excluded.checkpoint
                        """,
                        (
                            deck.key,
                            course.key,
                            deck.name,
                            deck.order,
                            deck.unlock_mastery,
                            deck.completion_mastery,
                            int(deck.checkpoint),
                        ),
                    )
            if deck_keys:
                placeholders = ",".join("?" for _ in deck_keys)
                db.execute(
                    f"DELETE FROM curriculum_decks WHERE key NOT IN ({placeholders}) AND course_key IN "
                    "(SELECT key FROM curriculum_courses WHERE curriculum_key=?)",
                    (*sorted(deck_keys), curriculum.key),
                )
            db.execute(
                "DELETE FROM deck_prerequisites WHERE deck_key IN "
                "(SELECT d.key FROM curriculum_decks d JOIN curriculum_courses c "
                "ON c.key=d.course_key WHERE c.curriculum_key=?)",
                (curriculum.key,),
            )
            for course in curriculum.courses:
                for deck in course.decks:
                    db.executemany(
                        "INSERT INTO deck_prerequisites(deck_key,prerequisite_key) VALUES(?,?)",
                        ((deck.key, prerequisite) for prerequisite in deck.prerequisite_keys),
                    )
        return {"courses": len(course_keys), "decks": len(deck_keys)}

    def list_curricula(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT c.*, COUNT(DISTINCT cc.key) course_count,
                  COUNT(DISTINCT cd.key) deck_count,
                  COUNT(DISTINCT cd.deck_id) bound_deck_count
                FROM curricula c
                LEFT JOIN curriculum_courses cc ON cc.curriculum_key=c.key
                LEFT JOIN curriculum_decks cd ON cd.course_key=cc.key
                GROUP BY c.key ORDER BY c.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_curriculum(self, key: str) -> Curriculum:
        with self._connect() as db:
            curriculum_row = db.execute(
                "SELECT * FROM curricula WHERE key=?", (key,)
            ).fetchone()
            if curriculum_row is None:
                raise StudyNotFoundError("curriculum not found")
            course_rows = db.execute(
                "SELECT * FROM curriculum_courses WHERE curriculum_key=? ORDER BY position,key",
                (key,),
            ).fetchall()
            courses: list[CurriculumCourse] = []
            for course_row in course_rows:
                deck_rows = db.execute(
                    "SELECT * FROM curriculum_decks WHERE course_key=? ORDER BY position,key",
                    (course_row["key"],),
                ).fetchall()
                decks: list[CurriculumDeck] = []
                for deck_row in deck_rows:
                    prerequisite_rows = db.execute(
                        "SELECT prerequisite_key FROM deck_prerequisites "
                        "WHERE deck_key=? ORDER BY prerequisite_key",
                        (deck_row["key"],),
                    ).fetchall()
                    decks.append(
                        CurriculumDeck(
                            key=str(deck_row["key"]),
                            name=str(deck_row["name"]),
                            order=int(deck_row["position"]),
                            prerequisite_keys=tuple(
                                str(row["prerequisite_key"]) for row in prerequisite_rows
                            ),
                            unlock_mastery=float(deck_row["unlock_mastery"]),
                            completion_mastery=float(deck_row["completion_mastery"]),
                            checkpoint=bool(deck_row["checkpoint"]),
                        )
                    )
                courses.append(
                    CurriculumCourse(
                        key=str(course_row["key"]),
                        name=str(course_row["name"]),
                        order=int(course_row["position"]),
                        decks=tuple(decks),
                        prerequisite_course_keys=tuple(
                            _parse_json_array(str(course_row["prerequisite_keys_json"]))
                        ),
                        completion_mastery=float(course_row["completion_mastery"]),
                    )
                )
        return Curriculum(
            key=str(curriculum_row["key"]),
            name=str(curriculum_row["name"]),
            version=str(curriculum_row["version"]),
            courses=tuple(courses),
            description=str(curriculum_row["description"]),
        )

    def bind_deck(self, curriculum_deck_key: str, deck_id: int) -> dict[str, Any]:
        with self._connect() as db:
            if db.execute("SELECT 1 FROM decks WHERE id=?", (deck_id,)).fetchone() is None:
                raise StudyNotFoundError("deck not found")
            cursor = db.execute(
                "UPDATE curriculum_decks SET deck_id=? WHERE key=?",
                (deck_id, curriculum_deck_key),
            )
            if cursor.rowcount == 0:
                raise StudyNotFoundError("curriculum deck not found")
        return self.get_curriculum_deck(curriculum_deck_key)

    def get_curriculum_deck(self, key: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT d.*, c.curriculum_key FROM curriculum_decks d
                JOIN curriculum_courses c ON c.key=d.course_key WHERE d.key=?
                """,
                (key,),
            ).fetchone()
            if row is None:
                raise StudyNotFoundError("curriculum deck not found")
            prerequisites = db.execute(
                "SELECT prerequisite_key FROM deck_prerequisites WHERE deck_key=? "
                "ORDER BY prerequisite_key",
                (key,),
            ).fetchall()
        payload = dict(row)
        payload["checkpoint"] = bool(payload["checkpoint"])
        payload["prerequisite_keys"] = [str(item["prerequisite_key"]) for item in prerequisites]
        return payload

    def get_review_state(self, card_id: int) -> CardReviewState:
        with self._connect() as db:
            if db.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone() is None:
                raise StudyNotFoundError("card not found")
            row = db.execute(
                "SELECT * FROM card_review_state WHERE card_id=?", (card_id,)
            ).fetchone()
        if row is None:
            return CardReviewState(card_id=card_id)
        return CardReviewState(**dict(row))

    def record_review(
        self,
        card_id: int,
        rating: ReviewRating,
        *,
        reviewed_at: datetime | None = None,
    ) -> CardReviewState:
        if rating not in {"again", "hard", "good", "easy", "skipped"}:
            raise ValueError("invalid review rating")
        current = self.get_review_state(card_id)
        moment = reviewed_at or datetime.now(UTC)
        stability, difficulty, interval_days, lapse_delta = _next_schedule(current, rating)
        due_at = None if rating == "skipped" else (moment + timedelta(days=interval_days)).isoformat()
        review_count = current.review_count + (0 if rating == "skipped" else 1)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO card_review_state(
                  card_id,rating,stability,difficulty,due_at,last_reviewed_at,
                  review_count,lapse_count
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(card_id) DO UPDATE SET
                  rating=excluded.rating,
                  stability=excluded.stability,
                  difficulty=excluded.difficulty,
                  due_at=excluded.due_at,
                  last_reviewed_at=excluded.last_reviewed_at,
                  review_count=excluded.review_count,
                  lapse_count=excluded.lapse_count
                """,
                (
                    card_id,
                    rating,
                    stability,
                    difficulty,
                    due_at,
                    moment.isoformat(),
                    review_count,
                    current.lapse_count + lapse_delta,
                ),
            )
        return self.get_review_state(card_id)

    def due_card_ids(self, *, at: datetime | None = None, limit: int = 100) -> tuple[int, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        moment = (at or datetime.now(UTC)).isoformat()
        with self._connect() as db:
            rows = db.execute(
                "SELECT card_id FROM card_review_state "
                "WHERE due_at IS NOT NULL AND due_at<=? ORDER BY due_at,card_id LIMIT ?",
                (moment, limit),
            ).fetchall()
        return tuple(int(row["card_id"]) for row in rows)


def _next_schedule(
    current: CardReviewState, rating: ReviewRating
) -> tuple[float, float, float, int]:
    if rating == "skipped":
        return current.stability, current.difficulty, 0.0, 0
    if rating == "again":
        return 0.25, min(10.0, current.difficulty + 0.8), 0.04, 1
    if rating == "hard":
        stability = max(0.5, current.stability * 1.2 if current.stability else 0.5)
        return stability, min(10.0, current.difficulty + 0.2), max(0.5, stability), 0
    if rating == "good":
        stability = max(1.0, current.stability * 2.5 if current.stability else 1.0)
        return stability, max(1.0, current.difficulty - 0.15), stability, 0
    stability = max(3.0, current.stability * 4.0 if current.stability else 3.0)
    return stability, max(1.0, current.difficulty - 0.5), stability, 0


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json_array(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(list(values), separators=(",", ":"))


def _parse_json_array(value: str) -> list[str]:
    import json

    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("invalid stored prerequisite list")
    return parsed


def review_state_payload(state: CardReviewState) -> dict[str, Any]:
    """Return a JSON-ready representation for future API endpoints."""
    return asdict(state)
