"""Portable Hermes Voice application with local Study features installed."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import ResponderPort
from hermes_voice.server import app as voice_app_module
from hermes_voice.server.app import create_app as create_voice_app
from hermes_voice.server.immediate_barge import ImmediateBargeInOrchestrator
from hermes_voice.server.orchestrator import ParrotResponder
from hermes_voice.study.curriculum import foundation_curriculum_skeleton
from hermes_voice.study.curriculum_responder import CurriculumStudyResponder
from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.install import install_study, wrap_responder_factory
from hermes_voice.study.store import StudyStore

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MakeResponder = Callable[[Callable[[sm.Event], None]], ResponderPort]


def _wrap_telegram_relay(store: StudyStore) -> None:
    from hermes_voice.io import telegram_telethon

    current = telegram_telethon.TelegramRelay
    original = getattr(current, "_hermes_study_original", current)
    curriculum_store = CurriculumStore(store.paths)
    curriculum_store.install_curriculum(foundation_curriculum_skeleton())

    class StudyTelegramRelay:
        _hermes_study_original = original

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            emit = kwargs.get("emit")
            if not callable(emit):
                raise TypeError("TelegramRelay requires an emit callback")

            holder: dict[str, CurriculumStudyResponder] = {}

            def bridge_emit(event: sm.Event) -> None:
                responder = holder.get("responder")
                if responder is None:
                    emit(event)
                    return
                responder.handle_delegate_event(event)

            delegate_kwargs = dict(kwargs)
            delegate_kwargs["emit"] = bridge_emit
            delegate = original(*args, **delegate_kwargs)
            responder = CurriculumStudyResponder(
                store=store,
                curriculum_store=curriculum_store,
                delegate=delegate,
                emit=emit,
            )
            holder["responder"] = responder
            self._study = responder

        async def send(self, text: str) -> None:
            await self._study.send(text)

        async def reset(self, chat_key: str) -> None:
            await self._study.reset(chat_key)

        async def close(self) -> None:
            await self._study.close()

        def __getattr__(self, name: str) -> Any:
            return getattr(self._study, name)

    vars(telegram_telethon)["TelegramRelay"] = StudyTelegramRelay


def _install_immediate_barge_in() -> None:
    """Use the orchestrator that interrupts TTS as soon as speech is confirmed."""
    vars(voice_app_module)["Orchestrator"] = ImmediateBargeInOrchestrator


def _install_voice_index(app: FastAPI) -> None:
    """Keep the Study navigation link without embedding a session panel."""
    app.router.routes[:] = [
        route for route in app.router.routes if getattr(route, "path", None) != "/"
    ]

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def study_voice_index() -> HTMLResponse:
        html = (_WEB_DIR / "index.html").read_text(encoding="utf-8")
        tab = '<a id="study-tab" href="/study">Study</a>'
        marker = "<h1>HERMES VOICE</h1>"
        if tab not in html:
            html = html.replace(marker, marker + "\n    " + tab, 1)
        return HTMLResponse(html)


def create_app(
    *,
    mode: str | None = None,
    make_responder: MakeResponder | None = None,
    study_store: StudyStore | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Create the existing portable app and layer Study onto it."""
    store = study_store or StudyStore()
    resolved_mode = (mode or os.environ.get("HV_MODE", "telegram")).strip().lower()

    wrapped_responder = make_responder
    if wrapped_responder is not None:
        wrapped_responder = wrap_responder_factory(store, wrapped_responder)
    elif resolved_mode == "telegram":
        _wrap_telegram_relay(store)
    elif resolved_mode != "echo":
        wrapped_responder = wrap_responder_factory(store, ParrotResponder)

    _install_immediate_barge_in()
    app = create_voice_app(
        mode=mode,
        make_responder=wrapped_responder,
        **kwargs,
    )
    install_study(app, store, _WEB_DIR)
    _install_voice_index(app)
    app.state.study_store = store
    return app
