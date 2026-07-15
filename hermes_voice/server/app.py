"""FastAPI shell: static web client + /ws voice endpoint.

Modes (HV_MODE or create_app(mode=...)):
- "telegram": the real thing - relay through Telegram via Telethon
- "parrot":   local loop, speaks your words back (no Telegram needed)
- "echo":     raw PCM echo, transport debugging only
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import ResponderPort, SttPort, TtsPort, VadPort
from hermes_voice.kit.protocol import (
    Cancel,
    ErrorMsg,
    Hello,
    ListTopics,
    Mute,
    ProtocolError,
    Ready,
    SelectChat,
    SelectTopic,
    TopicHistory,
    Topics,
    TopicSelected,
    decode_client_text,
    encode_audio_frame,
    encode_server_msg,
)
from hermes_voice.server.config import Config, load_config
from hermes_voice.server.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    ParrotResponder,
)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

MakeResponder = Callable[[Callable[[sm.Event], None]], ResponderPort]


def _build_speech_ports() -> tuple[VadPort, SttPort, TtsPort]:
    from hermes_voice.io.speech_factory import build_speech_ports

    return build_speech_ports()


async def _connect_telegram(config: Config) -> Any:
    from telethon import TelegramClient

    client = TelegramClient(
        str(config.telegram.session_path),
        config.telegram.api_id,
        config.telegram.api_hash,
    )
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError(
            "no authorized Telegram session - run: uv run python -m hermes_voice.scripts.login"
        )
    return client


async def _receive_hello(ws: WebSocket, expected_token: str) -> Hello | None:
    try:
        msg = decode_client_text(await ws.receive_text())
        if not isinstance(msg, Hello):
            raise ProtocolError("expected hello as first message")
        if expected_token and msg.token != expected_token:
            raise ProtocolError("invalid token")
        return msg
    except ProtocolError as exc:
        await ws.send_text(encode_server_msg(ErrorMsg(message=str(exc))))
        await ws.close()
        return None


async def _run_echo_session(ws: WebSocket) -> None:
    while True:
        event = await ws.receive()
        if event["type"] == "websocket.disconnect":
            return
        pcm = event.get("bytes")
        if pcm:
            await ws.send_bytes(encode_audio_frame(epoch=0, pcm=pcm))


async def _run_voice_session(
    ws: WebSocket,
    *,
    vad: VadPort,
    stt: SttPort,
    tts: TtsPort,
    make_responder: MakeResponder,
    initial_chat: str,
    orchestrator_config: OrchestratorConfig,
) -> None:
    orchestrator = Orchestrator(
        send_text=ws.send_text,
        send_bytes=ws.send_bytes,
        vad=vad,
        stt=stt,
        tts=tts,
        make_responder=make_responder,
        initial_chat=initial_chat,
        config=orchestrator_config,
    )
    run_task = asyncio.create_task(orchestrator.run())
    try:
        while True:
            event = await ws.receive()
            if event["type"] == "websocket.disconnect":
                return
            pcm = event.get("bytes")
            if pcm:
                orchestrator.feed_audio(pcm)
                continue
            raw = event.get("text")
            if raw is None:
                continue
            try:
                msg = decode_client_text(raw)
            except ProtocolError as exc:
                await ws.send_text(encode_server_msg(ErrorMsg(message=str(exc))))
                continue
            try:
                match msg:
                    case SelectChat(chat_key=chat_key):
                        await orchestrator.dispatch(sm.ChatSelected(chat_key=chat_key))
                    case ListTopics(query=query, limit=limit):
                        topics = await orchestrator.list_topics(query=query, limit=limit)
                        await ws.send_text(
                            encode_server_msg(
                                Topics(items=tuple(_topic_payload(topic) for topic in topics))
                            )
                        )
                    case SelectTopic(topic_id=topic_id, history_limit=history_limit):
                        await orchestrator.select_topic(topic_id)
                        await ws.send_text(encode_server_msg(TopicSelected(topic_id=topic_id)))
                        history = await orchestrator.load_topic_history(
                            topic_id,
                            limit=history_limit,
                        )
                        await ws.send_text(
                            encode_server_msg(
                                TopicHistory(
                                    topic_id=topic_id,
                                    messages=tuple(
                                        _topic_message_payload(message) for message in history
                                    ),
                                )
                            )
                        )
                    case Cancel():
                        orchestrator.emit(sm.CancelPressed())
                    case Mute() | Hello():
                        pass
            except (RuntimeError, ValueError) as exc:
                await ws.send_text(encode_server_msg(ErrorMsg(message=str(exc))))
    finally:
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run_task


def _topic_payload(topic: Any) -> dict[str, object]:
    return {
        "topic_id": topic.topic_id,
        "title": topic.title,
        "top_message_id": topic.top_message_id,
        "closed": topic.closed,
        "pinned": topic.pinned,
    }


def _topic_message_payload(message: Any) -> dict[str, object]:
    date = message.date.isoformat() if message.date is not None else None
    return {
        "message_id": message.message_id,
        "topic_id": message.topic_id,
        "role": "user" if message.is_outgoing else "agent",
        "text": message.text,
        "has_attachment": message.has_attachment,
        "date": date,
    }


def create_app(
    *,
    mode: str | None = None,
    vad: VadPort | None = None,
    stt: SttPort | None = None,
    tts: TtsPort | None = None,
    config: Config | None = None,
    telegram_client: Any = None,
    make_responder: MakeResponder | None = None,
    orchestrator_config: OrchestratorConfig | None = None,
) -> FastAPI:
    resolved_mode = mode or os.environ.get("HV_MODE", "telegram")
    telegram = resolved_mode == "telegram"
    resolved_config = (config or load_config()) if telegram else None

    speech_ports: dict[str, Any] = {"vad": vad, "stt": stt, "tts": tts}
    health = {"models": "n/a", "telegram": "n/a"}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        if telegram:
            assert resolved_config is not None
            client = telegram_client or await _connect_telegram(resolved_config)
            app.state.tg_client = client
            health["telegram"] = "connected"
        if resolved_mode != "echo":
            health["models"] = "loading"
            if speech_ports["vad"] is None:
                speech_ports["vad"], speech_ports["stt"], speech_ports["tts"] = (
                    _build_speech_ports()
                )
            for port in (speech_ports["stt"], speech_ports["tts"]):
                warmup = getattr(port, "warmup", None)
                if callable(warmup):
                    await warmup()
            health["models"] = "warm"
        try:
            yield
        finally:
            for port in speech_ports.values():
                close = getattr(port, "close", None)
                if callable(close):
                    close()
            if client is not None and telegram_client is None:
                await client.disconnect()

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_WEB_DIR / "index.html")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "mode": resolved_mode, **health}

    def session_setup() -> tuple[MakeResponder, str, OrchestratorConfig, Ready]:
        if telegram:
            assert resolved_config is not None
            chats = resolved_config.chats
            initial = next(iter(chats))

            def make_relay(emit: Callable[[sm.Event], None]) -> ResponderPort:
                from hermes_voice.io.telegram_telethon import TelegramRelay

                return TelegramRelay(client=app.state.tg_client, chats=chats, emit=emit)

            ready = Ready(
                chats=tuple({"key": c.key, "label": c.label} for c in chats.values()),
                active_chat=initial,
            )
            orch_config = orchestrator_config or OrchestratorConfig(
                wait_timeout_s=chats[initial].max_wait_s,
                wait_timeouts={key: chat.max_wait_s for key, chat in chats.items()},
            )
            return make_responder or make_relay, initial, orch_config, ready
        return (
            make_responder or ParrotResponder,
            "parrot",
            orchestrator_config or OrchestratorConfig(),
            Ready(chats=(), active_chat=None),
        )

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        expected_token = resolved_config.token if resolved_config else ""
        if await _receive_hello(ws, expected_token) is None:
            return
        make_responder, initial_chat, orch_config, ready = session_setup()
        await ws.send_text(encode_server_msg(ready))
        try:
            if resolved_mode == "echo":
                await _run_echo_session(ws)
                return
            await _run_voice_session(
                ws,
                vad=speech_ports["vad"],
                stt=speech_ports["stt"],
                tts=speech_ports["tts"],
                make_responder=make_responder,
                initial_chat=initial_chat,
                orchestrator_config=orch_config,
            )
        except WebSocketDisconnect:
            return

    app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")
    return app
