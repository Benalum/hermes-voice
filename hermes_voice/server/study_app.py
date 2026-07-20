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
from hermes_voice.server.app import create_app as create_voice_app
from hermes_voice.server.orchestrator import ParrotResponder
from hermes_voice.study.install import install_study, wrap_responder_factory
from hermes_voice.study.responder import StudyResponder
from hermes_voice.study.store import StudyStore

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MakeResponder = Callable[[Callable[[sm.Event], None]], ResponderPort]

_STUDY_PANEL = """
<section id="study-live" hidden aria-live="polite">
  <div class="study-live-heading">
    <div>
      <p>Active study session</p>
      <h2 id="study-live-title">Study</h2>
    </div>
    <span id="study-live-progress"></span>
  </div>
  <div id="study-live-question"></div>
  <div id="study-live-question-media" class="study-live-media"></div>
  <div id="study-live-answer" hidden></div>
  <div id="study-live-answer-media" class="study-live-media"></div>
  <div id="study-live-notes" hidden></div>
</section>
"""

_STUDY_STYLE = """
<style>
  #study-tab { color:#8ab4ff; text-decoration:none; font-weight:700; padding:.45rem .8rem;
    border:1px solid #33333e; border-radius:999px; background:#1c1c24; }
  #study-live { box-sizing:border-box; width:min(760px,calc(100% - 2rem)); margin:1rem auto 0;
    padding:1rem; border:1px solid #33333e; border-radius:14px; background:#181820; }
  .study-live-heading { display:flex; justify-content:space-between; gap:1rem; align-items:start; }
  .study-live-heading p { margin:0; color:#8ab4ff; font-size:.75rem; font-weight:700;
    letter-spacing:.1em; text-transform:uppercase; }
  .study-live-heading h2 { margin:.2rem 0 .8rem; font-size:1.1rem; }
  #study-live-progress { color:#a9a9b5; font-size:.85rem; }
  #study-live-question,#study-live-answer,#study-live-notes {
    white-space:pre-wrap; margin:.6rem 0; }
  #study-live-answer { padding-top:.7rem; border-top:1px solid #33333e; }
  #study-live-notes { color:#a9a9b5; }
  .study-live-media { display:grid; gap:.65rem; margin:.65rem 0; }
  .study-live-media img { display:block; width:100%; max-height:440px; object-fit:contain;
    background:#0b0b0f; border:1px solid #33333e; border-radius:10px; }
</style>
"""


def _wrap_telegram_relay(store: StudyStore) -> None:
    from hermes_voice.io import telegram_telethon

    current = telegram_telethon.TelegramRelay
    original = getattr(current, "_hermes_study_original", current)

    class StudyTelegramRelay:
        _hermes_study_original = original

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            emit = kwargs.get("emit")
            if not callable(emit):
                raise TypeError("TelegramRelay requires an emit callback")
            delegate = original(*args, **kwargs)
            self._study = StudyResponder(
                store=store,
                delegate=delegate,
                emit=emit,
                watch_sessions=True,
            )

        async def send(self, text: str) -> None:
            await self._study.send(text)

        async def reset(self, chat_key: str) -> None:
            await self._study.reset(chat_key)

        async def close(self) -> None:
            await self._study.close()

        def __getattr__(self, name: str) -> Any:
            return getattr(self._study, name)

    vars(telegram_telethon)["TelegramRelay"] = StudyTelegramRelay


def _install_voice_index(app: FastAPI) -> None:
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
        if 'id="study-live"' not in html:
            html = html.replace("</body>", _STUDY_PANEL + "\n</body>", 1)
        if "/static/study-live.mjs" not in html:
            script = '<script type="module" src="/static/study-live.mjs"></script>'
            html = html.replace("</body>", script + "\n</body>", 1)
        if "#study-live" not in html:
            html = html.replace("</head>", _STUDY_STYLE + "\n</head>", 1)
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

    app = create_voice_app(
        mode=mode,
        make_responder=wrapped_responder,
        **kwargs,
    )
    install_study(app, store, _WEB_DIR)
    _install_voice_index(app)
    app.state.study_store = store
    return app
