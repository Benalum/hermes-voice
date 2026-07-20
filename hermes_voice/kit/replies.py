"""Reply aggregation: decide when agent Telegram messages are speakable and
when the agent's turn has settled. Pure logic driven by explicit clock ticks.

A message becomes *speakable* once it has stopped being edited for
``edit_settle_s`` or a newer agent message exists (edit-streaming bots stop
editing a message when they move on). The turn *settles* after ``settle_s``
of quiet; a typing indicator holds settlement for ``typing_hold_s``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReplyConfig:
    edit_settle_s: float = 1.5
    settle_s: float = 2.5
    typing_hold_s: float = 6.0


@dataclass(frozen=True)
class Speak:
    message_id: int
    text: str


@dataclass(frozen=True)
class Settled:
    pass


ReplyEvent = Speak | Settled


@dataclass
class _Pending:
    text: str
    last_edit: float


@dataclass
class ReplyAggregator:
    config: ReplyConfig
    _anchor_id: int | None = field(default=None, init=False)
    _active: bool = field(default=False, init=False)
    _replied: bool = field(default=False, init=False)
    _pending: dict[int, _Pending] = field(default_factory=dict, init=False)
    _spoken: set[int] = field(default_factory=set, init=False)
    _last_activity: float = field(default=0.0, init=False)
    _typing_until: float = field(default=0.0, init=False)

    def anchor(self, message_id: int, now: float) -> None:
        self._anchor_id = message_id
        self._active = True
        self._replied = False
        self._last_activity = now

    def on_agent_message(self, message_id: int, text: str, now: float) -> None:
        if self._anchor_id is None or message_id <= self._anchor_id:
            return
        self._pending[message_id] = _Pending(text=text, last_edit=now)
        self._replied = True
        self._last_activity = now

    def on_agent_edit(self, message_id: int, text: str, now: float) -> None:
        pending = self._pending.get(message_id)
        if pending is None:
            return
        pending.text = text
        pending.last_edit = now
        self._last_activity = now

    def on_typing(self, now: float) -> None:
        self._last_activity = now
        self._typing_until = now + self.config.typing_hold_s

    def reset(self) -> None:
        self._anchor_id = None
        self._active = False
        self._replied = False
        self._pending.clear()
        self._spoken.clear()
        self._typing_until = 0.0

    def tick(self, now: float) -> tuple[ReplyEvent, ...]:
        events: list[ReplyEvent] = [*self._speakable(now)]
        if self._settles(now):
            self._active = False
            events.append(Settled())
        return tuple(events)

    def _speakable(self, now: float) -> list[Speak]:
        newest_id = max(self._pending, default=0)
        ready = [
            (message_id, pending.text)
            for message_id, pending in sorted(self._pending.items())
            if now - pending.last_edit >= self.config.edit_settle_s
            or message_id < newest_id
        ]
        for message_id, _ in ready:
            del self._pending[message_id]
            self._spoken.add(message_id)
        return [Speak(message_id=mid, text=text) for mid, text in ready]

    def _settles(self, now: float) -> bool:
        return (
            self._active
            and self._replied
            and not self._pending
            and now >= self._typing_until
            and now - self._last_activity >= self.config.settle_s
        )
