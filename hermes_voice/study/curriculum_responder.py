"""Voice commands for curriculum continuation, progress, reviews, and ratings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import ResponderPort
from hermes_voice.study.curriculum_runtime import CurriculumRuntime
from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.responder import StudyResponder, _normalize
from hermes_voice.study.store import StudyConflictError, StudyStore

_FOUNDATIONS = "mcat-medical-foundations-phase-1"
_RATINGS = {
    "again": "again",
    "mark again": "again",
    "i forgot": "again",
    "hard": "hard",
    "mark hard": "hard",
    "good": "good",
    "mark good": "good",
    "easy": "easy",
    "mark easy": "easy",
}


class CurriculumStudyResponder(StudyResponder):
    """Extend the existing Study responder without changing ordinary deck commands."""

    def __init__(
        self,
        *,
        store: StudyStore,
        curriculum_store: CurriculumStore,
        delegate: ResponderPort,
        emit: Callable[[sm.Event], None],
        watch_sessions: bool = False,
        poll_interval_s: float = 0.5,
    ) -> None:
        super().__init__(
            store=store,
            delegate=delegate,
            emit=emit,
            watch_sessions=watch_sessions,
            poll_interval_s=poll_interval_s,
        )
        self._curriculum_store = curriculum_store
        self._runtime = CurriculumRuntime(store, curriculum_store)

    def _handle(self, text: str, *, active: dict[str, Any] | None) -> str | None:
        normalized = _normalize(text)
        if normalized in {
            "continue curriculum",
            "continue my curriculum",
            "continue mcat",
            "continue foundations",
            "start next lesson",
        }:
            try:
                session = self._runtime.continue_curriculum(_FOUNDATIONS)
            except StudyConflictError as exc:
                return str(exc)
            self._remember(session)
            return self._question_prompt(session, prefix="Continuing your curriculum.")
        if normalized in {
            "curriculum progress",
            "mcat progress",
            "foundation progress",
            "how am i doing in the curriculum",
        }:
            return self._curriculum_progress()
        if normalized in {
            "start cumulative review",
            "start curriculum review",
            "review my weak cards",
            "review due cards",
        }:
            try:
                session = self._runtime.start_cumulative_review(_FOUNDATIONS)
            except StudyConflictError as exc:
                return str(exc)
            self._remember(session)
            return self._question_prompt(session, prefix="Starting your cumulative review.")
        return super()._handle(text, active=active)

    def _handle_active(self, session: dict[str, Any], normalized: str) -> str | None:
        rating = _RATINGS.get(normalized)
        if rating is not None:
            return self._grade_rating(session, rating)
        return super()._handle_active(session, normalized)

    def _grade_rating(self, session: dict[str, Any], rating: str) -> str:
        card = session.get("card")
        if card is None:
            return "This study session is finished."
        state = self._curriculum_store.record_review(int(card["id"]), rating)  # type: ignore[arg-type]
        outcome: Literal["correct", "wrong"] = (
            "wrong" if rating == "again" else "correct"
        )
        updated = self._store.grade(str(session["id"]), outcome)
        label = rating.capitalize()
        schedule = ""
        if state.due_at is not None:
            schedule = f" Next review is scheduled for {state.due_at}."
        if updated["status"] == "finished":
            self._remember(None)
            return f"{label} recorded.{schedule} {self._summary(updated)}"
        self._remember(updated)
        return self._question_prompt(updated, prefix=f"{label} recorded.{schedule}")

    def _curriculum_progress(self) -> str:
        progress = self._runtime.progress(_FOUNDATIONS)
        completed = sum(
            bool(deck["completed"])
            for course in progress["courses"]
            for deck in course["decks"]
        )
        total = sum(len(course["decks"]) for course in progress["courses"])
        next_deck = progress["next_deck"]
        next_text = (
            f" Your next lesson is {next_deck['name']}."
            if next_deck is not None
            else " There is no bound, unlocked lesson waiting right now."
        )
        return (
            f"Your curriculum mastery is {progress['overall_mastery']:.0%}. "
            f"You have completed {completed} of {total} lessons.{next_text}"
        )
