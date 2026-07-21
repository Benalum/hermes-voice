"""Attach Hermes Study routes and responder wrapping to the voice application."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import ResponderPort
from hermes_voice.study.api import create_study_router
from hermes_voice.study.curriculum import foundation_curriculum_skeleton
from hermes_voice.study.curriculum_api import create_curriculum_router
from hermes_voice.study.curriculum_responder import CurriculumStudyResponder
from hermes_voice.study.curriculum_runtime import CurriculumRuntime
from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.pack_api import create_pack_router
from hermes_voice.study.store import StudyStore

MakeResponder = Callable[[Callable[[sm.Event], None]], ResponderPort]


def install_study(app: FastAPI, store: StudyStore, web_dir: Path) -> None:
    curriculum_store = CurriculumStore(store.paths)
    curriculum_store.install_curriculum(foundation_curriculum_skeleton())
    runtime = CurriculumRuntime(store, curriculum_store)

    app.include_router(create_study_router(store))
    app.include_router(create_pack_router(store))
    app.include_router(create_curriculum_router(curriculum_store, runtime))
    app.state.curriculum_store = curriculum_store
    app.state.curriculum_runtime = runtime

    @app.get("/study")
    async def study_page() -> FileResponse:
        return FileResponse(web_dir / "study.html")


def wrap_responder_factory(
    store: StudyStore,
    make_responder: MakeResponder,
) -> MakeResponder:
    curriculum_store = CurriculumStore(store.paths)
    curriculum_store.install_curriculum(foundation_curriculum_skeleton())

    def make(emit: Callable[[sm.Event], None]) -> ResponderPort:
        return CurriculumStudyResponder(
            store=store,
            curriculum_store=curriculum_store,
            delegate=make_responder(emit),
            emit=emit,
            watch_sessions=True,
        )

    return make
