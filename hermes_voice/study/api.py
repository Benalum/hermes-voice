"""FastAPI routes for Hermes Study."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hermes_voice.study.store import StudyConflictError, StudyNotFoundError, StudyStore

Section = Literal["question", "answer", "notes"]
Outcome = Literal["correct", "wrong", "skipped"]


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)


class CardCreate(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    answer: str = Field(min_length=1, max_length=20000)
    notes: str = Field(default="", max_length=40000)


class CardUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=20000)
    answer: str | None = Field(default=None, min_length=1, max_length=20000)
    notes: str | None = Field(default=None, max_length=40000)


class MediaCreate(BaseModel):
    section: Section
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    data_base64: str = Field(min_length=1)


class SessionCreate(BaseModel):
    deck_id: int
    mode: Literal["ordered", "shuffled"] = "shuffled"
    limit: int | None = Field(default=None, ge=1, le=10000)


class GradeCreate(BaseModel):
    outcome: Outcome


def create_study_router(store: StudyStore) -> APIRouter:
    router = APIRouter(prefix="/api/study", tags=["study"])

    @router.get("/decks")
    def list_decks() -> dict[str, object]:
        return {"decks": store.list_decks()}

    @router.post("/decks", status_code=201)
    def create_deck(payload: DeckCreate) -> dict[str, object]:
        deck = _translate(lambda: store.create_deck(payload.name, payload.description))
        return {"deck": deck}

    @router.get("/decks/{deck_id}")
    def get_deck(deck_id: int) -> dict[str, object]:
        return {"deck": _translate(lambda: store.get_deck(deck_id))}

    @router.patch("/decks/{deck_id}")
    def update_deck(deck_id: int, payload: DeckUpdate) -> dict[str, object]:
        deck = _translate(
            lambda: store.update_deck(
                deck_id,
                name=payload.name,
                description=payload.description,
            )
        )
        return {"deck": deck}

    @router.delete("/decks/{deck_id}", status_code=204)
    def delete_deck(deck_id: int) -> Response:
        _translate(lambda: store.delete_deck(deck_id))
        return Response(status_code=204)

    @router.get("/decks/{deck_id}/cards")
    def list_cards(deck_id: int) -> dict[str, object]:
        return {"cards": _translate(lambda: store.list_cards(deck_id))}

    @router.post("/decks/{deck_id}/cards", status_code=201)
    def create_card(deck_id: int, payload: CardCreate) -> dict[str, object]:
        card = _translate(
            lambda: store.create_card(
                deck_id,
                question=payload.question,
                answer=payload.answer,
                notes=payload.notes,
            )
        )
        return {"card": card}

    @router.get("/cards/{card_id}")
    def get_card(card_id: int) -> dict[str, object]:
        return {"card": _translate(lambda: store.get_card(card_id))}

    @router.patch("/cards/{card_id}")
    def update_card(card_id: int, payload: CardUpdate) -> dict[str, object]:
        card = _translate(
            lambda: store.update_card(
                card_id,
                question=payload.question,
                answer=payload.answer,
                notes=payload.notes,
            )
        )
        return {"card": card}

    @router.delete("/cards/{card_id}", status_code=204)
    def delete_card(card_id: int) -> Response:
        _translate(lambda: store.delete_card(card_id))
        return Response(status_code=204)

    @router.post("/cards/{card_id}/media", status_code=201)
    def add_card_media(card_id: int, payload: MediaCreate) -> dict[str, object]:
        media = _translate(
            lambda: store.add_card_media(
                card_id,
                section=payload.section,
                filename=payload.filename,
                mime_type=payload.mime_type,
                data_base64=payload.data_base64,
            )
        )
        media.pop("path", None)
        return {"media": media}

    @router.delete("/cards/{card_id}/media/{section}/{media_id}", status_code=204)
    def remove_card_media(card_id: int, section: Section, media_id: str) -> Response:
        _translate(lambda: store.remove_card_media(card_id, media_id, section))
        return Response(status_code=204)

    @router.get("/media/{media_id}", response_class=FileResponse)
    def get_media(media_id: str) -> FileResponse:
        media = _translate(lambda: store.get_media(media_id))
        path = media["path"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="media file is missing")
        return FileResponse(
            path,
            media_type=str(media["mime_type"]),
            filename=str(media["original_filename"]),
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "ETag": f'"{media["sha256"]}"',
            },
        )

    @router.post("/sessions", status_code=201)
    def start_session(payload: SessionCreate) -> dict[str, object]:
        session = _translate(
            lambda: store.start_session(
                payload.deck_id,
                mode=payload.mode,
                limit=payload.limit,
            )
        )
        return {"session": session}

    @router.get("/sessions/current")
    def current_session() -> dict[str, object]:
        return {"session": store.current_session()}

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, object]:
        return {"session": _translate(lambda: store.get_session(session_id))}

    @router.post("/sessions/{session_id}/reveal")
    def reveal_answer(session_id: str) -> dict[str, object]:
        return {"session": _translate(lambda: store.reveal_answer(session_id))}

    @router.post("/sessions/{session_id}/grade")
    def grade(session_id: str, payload: GradeCreate) -> dict[str, object]:
        return {"session": _translate(lambda: store.grade(session_id, payload.outcome))}

    @router.post("/sessions/{session_id}/finish")
    def finish(session_id: str) -> dict[str, object]:
        return {"session": _translate(lambda: store.finish_session(session_id))}

    return router


def _translate[T](callback: Callable[[], T]) -> T:
    try:
        return callback()
    except StudyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StudyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
