"""FastAPI shell: static web client + /ws voice endpoint.

Modes (HV_MODE or create_app(mode=...)):
- "telegram": the real thing - relay through Telegram via Telethon
- "parrot":   local loop, speaks your words back (no Telegram needed)
- "echo":     raw PCM echo, transport debugging only
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import math
import mimetypes
import os
import secrets
from collections.abc import AsyncIterator, Callable, MutableMapping
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from hermes_voice.kit import session as sm
from hermes_voice.kit.ports import (
    ResponderPort,
    SpeakerVerifierPort,
    SttPort,
    TtsPort,
    VadPort,
)
from hermes_voice.kit.protocol import (
    Cancel,
    Chats,
    ErrorMsg,
    Hello,
    ListChats,
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
from hermes_voice.kit.speaker_gate import SpeakerGate
from hermes_voice.server.config import (
    Config,
    load_config,
    validate_config,
)
from hermes_voice.server.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    ParrotResponder,
)

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
# Windows does not consistently register the standard JavaScript MIME type for
# ES modules. StaticFiles consults this process-wide table when serving .mjs.
mimetypes.add_type("text/javascript", ".mjs")
_ALLOWED_MODES = frozenset({"telegram", "parrot", "echo"})
DEFAULT_HELLO_TIMEOUT_S = 10.0
VOICE_SESSION_BUSY_CLOSE_CODE = 1013
VOICE_SESSION_BUSY_MESSAGE = "voice session already active"

logger = logging.getLogger(__name__)

MakeResponder = Callable[[Callable[[sm.Event], None]], ResponderPort]


class _VoiceSessionGate:
    """Allow at most one active stateful voice session per application."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active = False

    async def acquire(self) -> bool:
        async with self._lock:
            if self._active:
                return False
            self._active = True
            return True

    def release(self) -> None:
        self._active = False


def _build_speech_ports() -> tuple[VadPort, SttPort, TtsPort]:
    from hermes_voice.io.speech_factory import build_speech_ports

    return build_speech_ports()


async def _disconnect_telegram_quietly(
    client: Any,
) -> None:
    """Disconnect a partially initialized Telegram client."""
    with contextlib.suppress(Exception):
        await client.disconnect()


async def _connect_telegram(config: Config) -> Any:
    from telethon import TelegramClient

    client = TelegramClient(
        str(config.telegram.session_path),
        config.telegram.api_id,
        config.telegram.api_hash,
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            raise RuntimeError(
                "no authorized Telegram session - run: uv run python -m hermes_voice.scripts.login"
            )

        return client
    except asyncio.CancelledError:
        await _disconnect_telegram_quietly(client)
        raise
    except Exception:
        await _disconnect_telegram_quietly(client)
        raise


async def _receive_hello(
    ws: WebSocket,
    expected_token: str,
    *,
    timeout_s: float,
) -> Hello | None:
    try:
        async with asyncio.timeout(timeout_s):
            event = await ws.receive()

        if event["type"] == "websocket.disconnect":
            return None

        raw = event.get("text")

        if raw is None:
            raise ProtocolError("expected a text hello as first message")

        msg = decode_client_text(raw)

        if not isinstance(msg, Hello):
            raise ProtocolError("expected hello as first message")

        if expected_token and not secrets.compare_digest(
            msg.token,
            expected_token,
        ):
            raise ProtocolError("invalid token")

        return msg
    except TimeoutError:
        await ws.send_text(encode_server_msg(ErrorMsg(message="hello timeout")))
        await ws.close(code=1008)
        return None
    except ProtocolError as exc:
        await ws.send_text(encode_server_msg(ErrorMsg(message=str(exc))))
        await ws.close(code=1008)
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
    speaker_gate: SpeakerVerifierPort | None = None,
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
        speaker_gate=speaker_gate,
    )
    run_task = asyncio.create_task(orchestrator.run())
    receive_task: asyncio.Task[MutableMapping[str, Any]] | None = None
    try:
        while True:
            receive_task = asyncio.create_task(ws.receive())
            done, _pending = await asyncio.wait(
                {receive_task, run_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if run_task in done:
                if not receive_task.done():
                    receive_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await receive_task
                receive_task = None
                try:
                    await run_task
                except asyncio.CancelledError:
                    return
                except Exception:
                    logger.exception("voice orchestrator failed")
                    with contextlib.suppress(Exception):
                        await ws.send_text(
                            encode_server_msg(ErrorMsg(message="voice session failed"))
                        )
                    with contextlib.suppress(Exception):
                        await ws.close(code=1011)
                return

            event = receive_task.result()
            receive_task = None
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
                    case ListChats(query=query, limit=limit):
                        chats = await orchestrator.list_chats(query=query, limit=limit)
                        await ws.send_text(
                            encode_server_msg(
                                Chats(items=tuple(_chat_payload(chat) for chat in chats))
                            )
                        )
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
                    case Mute(on=on):
                        await orchestrator.set_muted(on, source="button")
                    case Hello():
                        pass
            except Exception as exc:
                logger.exception("voice control request failed")
                await ws.send_text(encode_server_msg(ErrorMsg(message=str(exc))))
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receive_task
        if not run_task.done():
            run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task


def _chat_payload(chat: Any) -> dict[str, object]:
    return {
        "key": chat.key,
        "label": chat.label,
        "kind": chat.kind,
        "peer_id": chat.peer_id,
    }


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
    hello_timeout_s: float = DEFAULT_HELLO_TIMEOUT_S,
) -> FastAPI:
    raw_mode = mode if mode is not None else os.environ.get("HV_MODE", "telegram")
    resolved_mode = raw_mode.strip().lower()

    if resolved_mode not in _ALLOWED_MODES:
        allowed = ", ".join(sorted(_ALLOWED_MODES))
        raise ValueError(f"invalid Hermes Voice mode {raw_mode!r}; expected one of: {allowed}")

    if (
        isinstance(hello_timeout_s, bool)
        or not isinstance(
            hello_timeout_s,
            int | float,
        )
        or not math.isfinite(float(hello_timeout_s))
        or hello_timeout_s <= 0
    ):
        raise ValueError("hello_timeout_s must be a finite positive number")

    telegram = resolved_mode == "telegram"
    resolved_config = validate_config(config or load_config()) if telegram else None

    speech_ports: dict[str, Any] = {"vad": vad, "stt": stt, "tts": tts}
    voice_session_gate = _VoiceSessionGate()
    health = {"models": "n/a", "telegram": "n/a"}
    speaker_gate: dict[str, SpeakerVerifierPort | None] = {"port": None}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        owns_telegram_client = False
        try:
            if telegram:
                assert resolved_config is not None
                if telegram_client is None:
                    client = await _connect_telegram(resolved_config)
                    owns_telegram_client = True
                else:
                    client = telegram_client
                app.state.tg_client = client
                health["telegram"] = "connected"

            if resolved_mode != "echo":
                health["models"] = "loading"
                if speech_ports["vad"] is None:
                    speech_ports["vad"], speech_ports["stt"], speech_ports["tts"] = (
                        _build_speech_ports()
                    )
                if resolved_config is not None and resolved_config.speaker_gate.enabled:
                    remote_verifier = speech_ports["stt"]
                    if callable(getattr(remote_verifier, "verify_speaker", None)):
                        speaker_gate["port"] = remote_verifier
                        logger.info("speaker_gate enabled through shared speech service")
                    else:
                        local_gate = SpeakerGate(resolved_config.speaker_gate)
                        speaker_gate["port"] = local_gate
                        logger.info(
                            "speaker_gate enabled locally (threshold=%.3f)",
                            resolved_config.speaker_gate.threshold,
                        )
                for port in (speech_ports["stt"], speech_ports["tts"]):
                    warmup = getattr(port, "warmup", None)
                    if callable(warmup):
                        await warmup()
                health["models"] = "warm"

            yield
        finally:
            for name, port in speech_ports.items():
                close = getattr(port, "close", None)
                if not callable(close):
                    continue
                try:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("failed to close %s speech port", name)

            if client is not None and owns_telegram_client:
                await _disconnect_telegram_quietly(client)

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
        if (
            await _receive_hello(
                ws,
                expected_token,
                timeout_s=float(hello_timeout_s),
            )
            is None
        ):
            return
        if resolved_mode == "echo":
            await ws.send_text(encode_server_msg(Ready(chats=(), active_chat=None)))
            try:
                await _run_echo_session(ws)
            except WebSocketDisconnect:
                return
            return

        if not await voice_session_gate.acquire():
            await ws.send_text(encode_server_msg(ErrorMsg(message=VOICE_SESSION_BUSY_MESSAGE)))
            await ws.close(code=VOICE_SESSION_BUSY_CLOSE_CODE)
            return

        try:
            make_responder, initial_chat, orch_config, ready = session_setup()
            await ws.send_text(encode_server_msg(ready))
            await _run_voice_session(
                ws,
                vad=speech_ports["vad"],
                stt=speech_ports["stt"],
                tts=speech_ports["tts"],
                make_responder=make_responder,
                initial_chat=initial_chat,
                orchestrator_config=orch_config,
                speaker_gate=speaker_gate["port"],
            )
        except WebSocketDisconnect:
            return
        finally:
            voice_session_gate.release()

    app.mount("/static", StaticFiles(directory=_WEB_DIR), name="static")
    return app
