"""WebSocket wire protocol: JSON control frames + epoch-prefixed PCM audio frames."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass

_EPOCH_PREFIX = struct.Struct("<I")


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class Hello:
    token: str


@dataclass(frozen=True)
class SelectChat:
    chat_key: str


@dataclass(frozen=True)
class Mute:
    on: bool


@dataclass(frozen=True)
class Cancel:
    pass


ClientMsg = Hello | SelectChat | Mute | Cancel


@dataclass(frozen=True)
class Ready:
    chats: tuple[dict[str, str], ...]
    active_chat: str | None


@dataclass(frozen=True)
class StateMsg:
    name: str


@dataclass(frozen=True)
class Transcript:
    role: str
    text: str
    final: bool


@dataclass(frozen=True)
class AgentText:
    text: str
    message_id: int


@dataclass(frozen=True)
class SpeakStart:
    epoch: int
    sample_rate: int


@dataclass(frozen=True)
class SpeakStop:
    epoch: int


@dataclass(frozen=True)
class ErrorMsg:
    message: str


ServerMsg = Ready | StateMsg | Transcript | AgentText | SpeakStart | SpeakStop | ErrorMsg


def _require(obj: dict[str, object], field: str, kind: type) -> object:
    value = obj.get(field)
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        raise ProtocolError(f"field {field!r} must be {kind.__name__}")
    return value


def decode_client_text(raw: str) -> ClientMsg:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("control frame must be a JSON object")
    match obj.get("type"):
        case "hello":
            return Hello(token=str(_require(obj, "token", str)))
        case "select_chat":
            return SelectChat(chat_key=str(_require(obj, "chat_key", str)))
        case "mute":
            return Mute(on=bool(_require(obj, "on", bool)))
        case "cancel":
            return Cancel()
        case other:
            raise ProtocolError(f"unknown client message type: {other!r}")


def encode_server_msg(msg: ServerMsg) -> str:
    body: dict[str, object]
    match msg:
        case Ready(chats=chats, active_chat=active_chat):
            body = {"type": "ready", "chats": list(chats), "active_chat": active_chat}
        case StateMsg(name=name):
            body = {"type": "state", "name": name}
        case Transcript(role=role, text=text, final=final):
            body = {"type": "transcript", "role": role, "text": text, "final": final}
        case AgentText(text=text, message_id=message_id):
            body = {"type": "agent_text", "text": text, "message_id": message_id}
        case SpeakStart(epoch=epoch, sample_rate=sample_rate):
            body = {"type": "speak_start", "epoch": epoch, "sample_rate": sample_rate}
        case SpeakStop(epoch=epoch):
            body = {"type": "speak_stop", "epoch": epoch}
        case ErrorMsg(message=message):
            body = {"type": "error", "message": message}
    return json.dumps(body)


def encode_audio_frame(epoch: int, pcm: bytes) -> bytes:
    if not 0 <= epoch < 2**32:
        raise ProtocolError(f"epoch out of range: {epoch}")
    return _EPOCH_PREFIX.pack(epoch) + pcm


def decode_audio_frame(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < _EPOCH_PREFIX.size:
        raise ProtocolError("audio frame shorter than epoch prefix")
    (epoch,) = _EPOCH_PREFIX.unpack_from(frame)
    return epoch, frame[_EPOCH_PREFIX.size :]
