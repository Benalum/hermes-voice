"""Runtime curriculum progress, unlocking, continuation, and cumulative reviews."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from hermes_voice.study.curriculum import (
    MasterySnapshot,
    ReviewCandidate,
    build_cumulative_review,
    course_mastery,
    course_unlock_decision,
    deck_unlock_decision,
)
from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.store import StudyConflictError, StudyNotFoundError, StudyStore


class CurriculumRuntime:
    """Combine stored Study activity with curriculum progression policy."""

    def __init__(self, study: StudyStore, curricula: CurriculumStore) -> None:
        self.study = study
        self.curricula = curricula

    def progress(self, curriculum_key: str) -> dict[str, Any]:
        curriculum = self.curricula.get_curriculum(curriculum_key)
        snapshots = self._mastery_snapshots(curriculum_key)
        bound = self._bound_decks(curriculum_key)
        courses: list[dict[str, Any]] = []
        next_deck: dict[str, Any] | None = None

        for course in curriculum.ordered_courses():
            course_decision = course_unlock_decision(course, curriculum, snapshots)
            course_payload: dict[str, Any] = {
                "key": course.key,
                "name": course.name,
                "order": course.order,
                "mastery": course_mastery(course, snapshots),
                "unlocked": course_decision.unlocked,
                "reasons": list(course_decision.reasons),
                "decks": [],
            }
            for deck in sorted(course.decks, key=lambda item: (item.order, item.key)):
                decision = deck_unlock_decision(deck, snapshots)
                snapshot = snapshots.get(deck.key, MasterySnapshot())
                deck_id = bound.get(deck.key)
                completed = snapshot.mastery >= deck.completion_mastery
                unlocked = course_decision.unlocked and decision.unlocked
                payload = {
                    "key": deck.key,
                    "name": deck.name,
                    "order": deck.order,
                    "deck_id": deck_id,
                    "bound": deck_id is not None,
                    "mastery": snapshot.mastery,
                    "reviewed": snapshot.reviewed,
                    "total_cards": snapshot.total_cards,
                    "due_cards": snapshot.due_cards,
                    "completed": completed,
                    "unlocked": unlocked,
                    "reasons": list(course_decision.reasons + decision.reasons),
                    "checkpoint": deck.checkpoint,
                }
                course_payload["decks"].append(payload)
                if next_deck is None and unlocked and deck_id is not None and not completed:
                    next_deck = payload
            courses.append(course_payload)

        return {
            "curriculum": {
                "key": curriculum.key,
                "name": curriculum.name,
                "version": curriculum.version,
                "description": curriculum.description,
            },
            "courses": courses,
            "next_deck": next_deck,
            "overall_mastery": (
                sum(float(course["mastery"]) for course in courses) / len(courses)
                if courses
                else 0.0
            ),
        }

    def continue_curriculum(self, curriculum_key: str) -> dict[str, Any]:
        progress = self.progress(curriculum_key)
        next_deck = progress["next_deck"]
        if next_deck is None:
            raise StudyConflictError(
                "No unlocked curriculum deck with remaining mastery work is currently available."
            )
        return self.study.start_session(int(next_deck["deck_id"]), mode="ordered")

    def start_cumulative_review(
        self,
        curriculum_key: str,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        progress = self.progress(curriculum_key)
        unlocked_keys = {
            str(deck["key"])
            for course in progress["courses"]
            for deck in course["decks"]
            if deck["unlocked"] and deck["bound"]
        }
        candidates = self._review_candidates(curriculum_key, unlocked_keys)
        plan = build_cumulative_review(candidates, limit=limit, now=now)
        if not plan.card_ids:
            raise StudyConflictError("There are no unlocked curriculum cards available for review.")
        anchor = self._anchor_deck_id(curriculum_key, plan.card_ids)
        return self._start_card_session(anchor, plan.card_ids, mode="cumulative")

    def _mastery_snapshots(self, curriculum_key: str) -> dict[str, MasterySnapshot]:
        now = datetime.now(UTC).isoformat()
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT cd.key,
                  COUNT(DISTINCT c.id) total_cards,
                  COUNT(DISTINCT CASE WHEN crs.review_count > 0 THEN c.id END) reviewed_cards,
                  SUM(CASE WHEN crs.rating='again' THEN 1 ELSE 0 END) again_count,
                  SUM(CASE WHEN crs.rating='hard' THEN 1 ELSE 0 END) hard_count,
                  SUM(CASE WHEN crs.rating='good' THEN 1 ELSE 0 END) good_count,
                  SUM(CASE WHEN crs.rating='easy' THEN 1 ELSE 0 END) easy_count,
                  SUM(CASE WHEN crs.rating='skipped' THEN 1 ELSE 0 END) skipped_count,
                  SUM(CASE WHEN crs.due_at IS NOT NULL AND crs.due_at<=? THEN 1 ELSE 0 END) due_cards
                FROM curriculum_decks cd
                JOIN curriculum_courses cc ON cc.key=cd.course_key
                LEFT JOIN cards c ON c.deck_id=cd.deck_id
                LEFT JOIN card_review_state crs ON crs.card_id=c.id
                WHERE cc.curriculum_key=?
                GROUP BY cd.key
                """,
                (now, curriculum_key),
            ).fetchall()
        result: dict[str, MasterySnapshot] = {}
        for row in rows:
            reviewed = int(row["reviewed_cards"] or 0)
            result[str(row["key"])] = MasterySnapshot(
                attempts=reviewed,
                again=int(row["again_count"] or 0),
                hard=int(row["hard_count"] or 0),
                good=int(row["good_count"] or 0),
                easy=int(row["easy_count"] or 0),
                skipped=int(row["skipped_count"] or 0),
                due_cards=int(row["due_cards"] or 0),
                total_cards=int(row["total_cards"] or 0),
            )
        return result

    def _bound_decks(self, curriculum_key: str) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT cd.key,cd.deck_id FROM curriculum_decks cd
                JOIN curriculum_courses cc ON cc.key=cd.course_key
                WHERE cc.curriculum_key=? AND cd.deck_id IS NOT NULL
                """,
                (curriculum_key,),
            ).fetchall()
        return {str(row["key"]): int(row["deck_id"]) for row in rows}

    def _review_candidates(
        self, curriculum_key: str, unlocked_keys: set[str]
    ) -> list[ReviewCandidate]:
        if not unlocked_keys:
            return []
        placeholders = ",".join("?" for _ in unlocked_keys)
        query = f"""
            SELECT c.id card_id,cd.key deck_key,crs.due_at,crs.last_reviewed_at,
              crs.lapse_count,crs.review_count,crs.rating,
              EXISTS(SELECT 1 FROM card_media cm WHERE cm.card_id=c.id) image_card
            FROM curriculum_decks cd
            JOIN curriculum_courses cc ON cc.key=cd.course_key
            JOIN cards c ON c.deck_id=cd.deck_id
            LEFT JOIN card_review_state crs ON crs.card_id=c.id
            WHERE cc.curriculum_key=? AND cd.key IN ({placeholders})
        """
        with self._connect() as db:
            rows = db.execute(query, (curriculum_key, *sorted(unlocked_keys))).fetchall()
        candidates: list[ReviewCandidate] = []
        for row in rows:
            rating = row["rating"]
            mastery = {
                None: 0.0,
                "again": 0.0,
                "hard": 0.5,
                "good": 0.85,
                "easy": 1.0,
                "skipped": 0.0,
            }[rating]
            candidates.append(
                ReviewCandidate(
                    card_id=int(row["card_id"]),
                    deck_key=str(row["deck_key"]),
                    due_at=_parse_time(row["due_at"]),
                    mastery=mastery,
                    lapses=int(row["lapse_count"] or 0),
                    last_reviewed_at=_parse_time(row["last_reviewed_at"]),
                    newly_unlocked=int(row["review_count"] or 0) == 0,
                    image_card=bool(row["image_card"]),
                )
            )
        return candidates

    def _anchor_deck_id(self, curriculum_key: str, card_ids: tuple[int, ...]) -> int:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT c.deck_id FROM cards c
                JOIN curriculum_decks cd ON cd.deck_id=c.deck_id
                JOIN curriculum_courses cc ON cc.key=cd.course_key
                WHERE cc.curriculum_key=? AND c.id=?
                """,
                (curriculum_key, card_ids[0]),
            ).fetchone()
        if row is None:
            raise StudyNotFoundError("review anchor deck not found")
        return int(row["deck_id"])

    def _start_card_session(
        self, anchor_deck_id: int, card_ids: tuple[int, ...], *, mode: str
    ) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        with self._connect() as db:
            db.execute(
                "UPDATE study_sessions SET status='finished',ended_at=COALESCE(ended_at,?) "
                "WHERE status='active'",
                (now,),
            )
            db.execute(
                "INSERT INTO study_sessions(id,deck_id,mode,status,card_order_json,started_at) "
                "VALUES(?,?,?,'active',?,?)",
                (session_id, anchor_deck_id, mode, json.dumps(card_ids), now),
            )
        return self.study.get_session(session_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.curricula.paths.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
