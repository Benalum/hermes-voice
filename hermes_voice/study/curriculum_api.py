"""HTTP endpoints for curriculum progression and spaced review state."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from hermes_voice.study.curriculum import Curriculum, foundation_curriculum_skeleton
from hermes_voice.study.curriculum_runtime import CurriculumRuntime
from hermes_voice.study.curriculum_store import CurriculumStore, review_state_payload
from hermes_voice.study.store import StudyConflictError, StudyNotFoundError


class DeckBinding(BaseModel):
    deck_id: int = Field(gt=0)


class ReviewSubmission(BaseModel):
    rating: Literal["again", "hard", "good", "easy", "skipped"]
    reviewed_at: datetime | None = None


class ReviewSessionRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)


def create_curriculum_router(
    store: CurriculumStore,
    runtime: CurriculumRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/api/study", tags=["study-curriculum"])

    @router.get("/curricula")
    def list_curricula() -> dict[str, object]:
        return {"curricula": store.list_curricula()}

    @router.post("/curricula/mcat-medical-foundations-phase-1/install")
    def install_foundations() -> dict[str, object]:
        curriculum = foundation_curriculum_skeleton()
        installed = store.install_curriculum(curriculum)
        return {
            "curriculum": _curriculum_payload(store.get_curriculum(curriculum.key)),
            "installed": installed,
        }

    @router.get("/curricula/{curriculum_key}")
    def get_curriculum(curriculum_key: str) -> dict[str, object]:
        try:
            curriculum = store.get_curriculum(curriculum_key)
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"curriculum": _curriculum_payload(curriculum)}

    @router.get("/curricula/{curriculum_key}/progress")
    def get_progress(curriculum_key: str) -> dict[str, object]:
        try:
            return {"progress": runtime.progress(curriculum_key)}
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/curricula/{curriculum_key}/continue")
    def continue_curriculum(curriculum_key: str) -> dict[str, object]:
        try:
            return {"session": runtime.continue_curriculum(curriculum_key)}
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StudyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/curricula/{curriculum_key}/review-session")
    def start_review_session(
        curriculum_key: str,
        payload: ReviewSessionRequest,
    ) -> dict[str, object]:
        try:
            session = runtime.start_cumulative_review(curriculum_key, limit=payload.limit)
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StudyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"session": session}

    @router.post("/curriculum-decks/{curriculum_deck_key}/bind")
    def bind_deck(curriculum_deck_key: str, payload: DeckBinding) -> dict[str, object]:
        try:
            deck = store.bind_deck(curriculum_deck_key, payload.deck_id)
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"curriculum_deck": deck}

    @router.get("/cards/{card_id}/review-state")
    def get_review_state(card_id: int) -> dict[str, object]:
        try:
            state = store.get_review_state(card_id)
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"review_state": review_state_payload(state)}

    @router.post("/cards/{card_id}/review")
    def record_review(card_id: int, payload: ReviewSubmission) -> dict[str, object]:
        reviewed_at = payload.reviewed_at
        if reviewed_at is not None and reviewed_at.tzinfo is None:
            reviewed_at = reviewed_at.replace(tzinfo=UTC)
        try:
            state = store.record_review(card_id, payload.rating, reviewed_at=reviewed_at)
        except StudyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"review_state": review_state_payload(state)}

    @router.get("/reviews/due")
    def due_reviews(
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        at: datetime | None = None,
    ) -> dict[str, object]:
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return {"card_ids": store.due_card_ids(at=at, limit=limit)}

    return router


def _curriculum_payload(curriculum: Curriculum) -> dict[str, object]:
    return asdict(curriculum)
