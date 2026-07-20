"""WebSocket wire protocol: JSON control frames + epoch-prefixed PCM audio frames."""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from typing import cast

_EPOCH_PREFIX = struct.Struct("<I")

MIN_SPEECH_SPEED = 0.5
MAX_SPEECH_SPEED = 2.0
MIN_END_SILENCE_MS = 300
MAX_END_SILENCE_MS = 5000


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
class VoiceSettings:
    speech_speed: float
    end_silence_ms: int


@dataclass(frozen=True)
class ListChats:
    query: str = ""
    limit: int = 100


@dataclass(frozen=True)
class ListTopics:
    query: str = ""
    limit: int = 100


@dataclass(frozen=True)
class SelectTopic:
    topic_id: int
    history_limit: int = 50


@dataclass(frozen=True)
class Cancel:
    pass


ClientMsg = (
    Hello | SelectChat | ListChats | ListTopics | SelectTopic | Mute | VoiceSettings | Cancel
)


@dataclass(frozen=True)
class Ready:
    chats: tuple[dict[str, str], ...]
    active_chat: str | None


@dataclass(frozen=True)
class MuteState:
    on: bool
    source: str


@dataclass(frozen=True)
class VoiceSettingsState:
    speech_speed: float
    end_silence_ms: int


@dataclass(frozen=True)
class Chats:
    items: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class Topics:
    items: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class TopicSelected:
    topic_id: int | None


@dataclass(frozen=True)
class TopicHistory:
    topic_id: int
    messages: tuple[dict[str, object], ...]


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
    flush: bool = False


@dataclass(frozen=True)
class ErrorMsg:
    message: str


ServerMsg = (
    Ready
    | MuteState
    | VoiceSettingsState
    | Chats
    | Topics
    | TopicSelected
    | TopicHistory
    | StateMsg
    | Transcript
    | AgentText
    | SpeakStart
    | SpeakStop
    | ErrorMsg
)


def _require(obj: dict[str, object], field: str, kind: type) -> object:
    value = obj.get(field)
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        raise ProtocolError(f"field {field!r} must be {kind.__name__}")
    return value


def _require_number(
    obj: dict[str, object],
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = obj.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProtocolError(f"field {field!r} must be number")
    resolved = float(value)
    if not math.isfinite(resolved) or not minimum <= resolved <= maximum:
        raise ProtocolError(f"field {field!r} must be between {minimum} and {maximum}")
    return resolved


def _optional_int(
    obj: dict[str, object],
    field: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = obj.get(field, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProtocolError(f"field {field!r} must be int")
    if not minimum <= value <= maximum:
        raise ProtocolError(f"field {field!r} must be between {minimum} and {maximum}")
    return value


def _optional_str(obj: dict[str, object], field: str, *, default: str = "") -> str:
    value = obj.get(field, default)
    if not isinstance(value, str):
        raise ProtocolError(f"field {field!r} must be str")
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
        case "list_chats":
            return ListChats(
                query=_optional_str(obj, "query").strip(),
                limit=_optional_int(
                    obj,
                    "limit",
                    default=100,
                    minimum=1,
                    maximum=500,
                ),
            )
        case "list_topics":
            return ListTopics(
                query=_optional_str(obj, "query").strip(),
                limit=_optional_int(
                    obj,
                    "limit",
                    default=100,
                    minimum=1,
                    maximum=100,
                ),
            )
        case "select_topic":
            topic_id = cast(int, _require(obj, "topic_id", int))
            if topic_id <= 0:
                raise ProtocolError("field 'topic_id' must be a positive integer")
            return SelectTopic(
                topic_id=topic_id,
                history_limit=_optional_int(
                    obj,
                    "history_limit",
                    default=50,
                    minimum=1,
                    maximum=100,
                ),
            )
        case "mute":
            return Mute(on=bool(_require(obj, "on", bool)))
        case "voice_settings":
            end_silence_ms = cast(int, _require(obj, "end_silence_ms", int))
            if not MIN_END_SILENCE_MS <= end_silence_ms <= MAX_END_SILENCE_MS:
                raise ProtocolError(
                    "field 'end_silence_ms' must be between "
                    f"{MIN_END_SILENCE_MS} and {MAX_END_SILENCE_MS}"
                )
            return VoiceSettings(
                speech_speed=_require_number(
                    obj,
                    "speech_speed",
                    minimum=MIN_SPEECH_SPEED,
                    maximum=MAX_SPEECH_SPEED,
                ),
                end_silence_ms=end_silence_ms,
            )
        case "cancel":
            return Cancel()
        case other:
            raise ProtocolError(f"unknown client message type: {other!r}")


def encode_server_msg(msg: ServerMsg) -> str:
    body: dict[str, object]
    match msg:
        case Ready(chats=chats, active_chat=active_chat):
            body = {"type": "ready", "chats": list(chats), "active_chat": active_chat}
        case Chats(items=items):
            body = {"type": "chats", "chats": list(items)}
        case MuteState(on=on, source=source):
            body = {"type": "mute_state", "on": on, "source": source}
        case VoiceSettingsState(
            speech_speed=speech_speed,
            end_silence_ms=end_silence_ms,
        ):
            body = {
                "type": "voice_settings_state",
                "speech_speed": speech_speed,
                "end_silence_ms": end_silence_ms,
            }
        case Topics(items=items):
            body = {"type": "topics", "topics": list(items)}
        case TopicSelected(topic_id=topic_id):
            body = {"type": "topic_selected", "topic_id": topic_id}
        case TopicHistory(topic_id=topic_id, messages=messages):
            body = {
                "type": "topic_history",
                "topic_id": topic_id,
                "messages": list(messages),
            }
        case StateMsg(name=name):
            body = {"type": "state", "name": name}
        case Transcript(role=role, text=text, final=final):
            body = {"type": "transcript", "role": role, "text": text, "final": final}
        case AgentText(text=text, message_id=message_id):
            body = {"type": "agent_text", "text": text, "message_id": message_id}
        case SpeakStart(epoch=epoch, sample_rate=sample_rate):
            body = {"type": "speak_start", "epoch": epoch, "sample_rate": sample_rate}
        case SpeakStop(epoch=epoch, flush=flush):
            body = {"type": "speak_stop", "epoch": epoch, "flush": flush}
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
