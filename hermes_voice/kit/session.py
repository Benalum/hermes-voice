"""Pure session state machine: (session, event) -> (session, effects).

Effects are data; the server orchestrator interprets them (send WS messages,
call STT/TTS, relay to Telegram). Nothing here touches I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

WAIT_NOTICE = "Still waiting on the agent."


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    WAITING = "waiting"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class Session:
    state: State
    turn_open: bool
    chat_key: str | None

    @staticmethod
    def initial() -> Session:
        return Session(state=State.IDLE, turn_open=False, chat_key=None)


# --- Events ---


@dataclass(frozen=True)
class ChatSelected:
    chat_key: str


@dataclass(frozen=True)
class SpeechEnded:
    pcm: bytes


@dataclass(frozen=True)
class BargedIn:
    pass


@dataclass(frozen=True)
class SttCompleted:
    text: str


@dataclass(frozen=True)
class AgentSpeakable:
    text: str
    message_id: int


@dataclass(frozen=True)
class TurnSettled:
    pass


@dataclass(frozen=True)
class MaxWaitTimedOut:
    pass


@dataclass(frozen=True)
class TtsFinished:
    pass


@dataclass(frozen=True)
class CancelPressed:
    pass


Event = (
    ChatSelected
    | SpeechEnded
    | BargedIn
    | SttCompleted
    | AgentSpeakable
    | TurnSettled
    | MaxWaitTimedOut
    | TtsFinished
    | CancelPressed
)


# --- Effects ---


@dataclass(frozen=True)
class Transcribe:
    pcm: bytes


@dataclass(frozen=True)
class SendTranscript:
    text: str


@dataclass(frozen=True)
class RelaySend:
    text: str


@dataclass(frozen=True)
class SendAgentText:
    text: str
    message_id: int


@dataclass(frozen=True)
class EnqueueSpeech:
    text: str


@dataclass(frozen=True)
class StopSpeaking:
    pass


@dataclass(frozen=True)
class ResetReplies:
    chat_key: str


Effect = (
    Transcribe
    | SendTranscript
    | RelaySend
    | SendAgentText
    | EnqueueSpeech
    | StopSpeaking
    | ResetReplies
)

_Result = tuple[Session, tuple[Effect, ...]]


def advance(session: Session, event: Event) -> _Result:
    match event:
        case ChatSelected(chat_key=chat_key):
            effects: tuple[Effect, ...] = (ResetReplies(chat_key=chat_key),)
            if session.state is State.SPEAKING:
                effects = (StopSpeaking(), *effects)
            return (
                Session(state=State.LISTENING, turn_open=False, chat_key=chat_key),
                effects,
            )
        case _ if session.state is State.IDLE:
            return session, ()
        case SpeechEnded(pcm=pcm) if session.state in (State.LISTENING, State.WAITING):
            return replace(session, state=State.TRANSCRIBING), (Transcribe(pcm=pcm),)
        case SttCompleted(text=text) if session.state is State.TRANSCRIBING:
            if not text.strip():
                return replace(session, state=State.LISTENING), ()
            return (
                replace(session, state=State.WAITING, turn_open=True),
                (SendTranscript(text=text), RelaySend(text=text)),
            )
        case AgentSpeakable(text=text, message_id=message_id) if session.state in (
            State.WAITING,
            State.SPEAKING,
            State.LISTENING,
        ):
            return (
                replace(session, state=State.SPEAKING),
                (SendAgentText(text=text, message_id=message_id), EnqueueSpeech(text=text)),
            )
        case TurnSettled():
            settled = replace(session, turn_open=False)
            if session.state is State.WAITING:
                return replace(settled, state=State.LISTENING), ()
            return settled, ()
        case TtsFinished() if session.state is State.SPEAKING:
            next_state = State.WAITING if session.turn_open else State.LISTENING
            return replace(session, state=next_state), ()
        case BargedIn() if session.state is State.SPEAKING:
            return replace(session, state=State.LISTENING), (StopSpeaking(),)
        case CancelPressed() if session.state is State.SPEAKING:
            next_state = State.WAITING if session.turn_open else State.LISTENING
            return replace(session, state=next_state), (StopSpeaking(),)
        case MaxWaitTimedOut() if session.state is State.WAITING:
            return (
                replace(session, state=State.SPEAKING, turn_open=False),
                (EnqueueSpeech(text=WAIT_NOTICE),),
            )
        case _:
            return session, ()
