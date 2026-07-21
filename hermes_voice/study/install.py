"""Attach Hermes Study routes and responder wrapping to the voice application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import ResponderPort
from hermes_voice.study.api import create_study_router
from hermes_voice.study.pack_api import create_pack_router
from hermes_voice.study.responder import StudyResponder
from hermes_voice.study.store import StudyStore

MakeResponder = Callable[[Callable[[sm.Event], None]], ResponderPort]


def install_study(app: FastAPI, store: StudyStore, web_dir: Path) -> None:
    app.include_router(create_study_router(store))
    app.include_router(create_pack_router(store))

    @app.get("/study")
    async def study_page() -> FileResponse:
        return FileResponse(web_dir / "study.html")


def wrap_responder_factory(
    store: StudyStore,
    make_responder: MakeResponder,
) -> MakeResponder:
    def make(emit: Callable[[sm.Event], None]) -> ResponderPort:
        return StudyResponder(
            store=store,
            delegate=make_responder(emit),
            emit=emit,
            watch_sessions=True,
        )

    return make
