"""Relay wiring tests with a fake Telethon client - no network, no session."""

from types import SimpleNamespace
from typing import Any

from telethon.tl import types

from hermes_voice.io.telegram_telethon import TelegramRelay
from hermes_voice.kit.replies import ReplyConfig
from hermes_voice.kit.session import AgentSpeakable, Event, TurnSettled
from hermes_voice.server.config import ChatConfig

CHATS = {
    "hermes": ChatConfig(key="hermes", peer="@hermes_bot", label="Hermes", max_wait_s=180.0),
    "ops": ChatConfig(key="ops", peer=222, label="Ops", max_wait_s=300.0),
}


class FakeClient:
    def __init__(self) -> None:
        self.handlers: list[tuple[Any, str]] = []
        self.sent: list[tuple[Any, str]] = []
        self.entities = {"@hermes_bot": types.User(id=111), 222: types.User(id=222)}
        self.next_message_id = 10

    def add_event_handler(self, callback: Any, event_filter: Any) -> None:
        self.handlers.append((callback, type(event_filter).__name__))

    async def get_entity(self, peer: Any) -> Any:
        return self.entities[peer]

    async def send_message(self, entity: Any, text: str) -> Any:
        self.sent.append((entity, text))
        self.next_message_id += 1
        return SimpleNamespace(id=self.next_message_id)

    async def fire_new_message(
        self, chat_id: int, message_id: int, text: str, *, out: bool = False
    ) -> None:
        event = SimpleNamespace(
            chat_id=chat_id,
            message=SimpleNamespace(id=message_id, out=out, message=text, media=None),
        )
        for callback, name in self.handlers:
            if name == "NewMessage":
                await callback(event)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_relay() -> tuple[TelegramRelay, FakeClient, Clock, list[Event]]:
    client = FakeClient()
    clock = Clock()
    events: list[Event] = []
    relay = TelegramRelay(
        client=client,
        chats=CHATS,
        emit=events.append,
        reply_config=ReplyConfig(edit_settle_s=1.5, settle_s=2.5, typing_hold_s=6.0),
        clock=clock,
    )
    return relay, client, clock, events


class TestTelegramRelay:
    async def test_send_posts_into_the_active_chat(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")
        await relay.send("do the thing")
        assert client.sent == [(client.entities["@hermes_bot"], "do the thing")]

    async def test_agent_reply_becomes_speakable_then_settles(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        clock.now = 1.0
        await relay.send("do the thing")
        clock.now = 2.0
        await client.fire_new_message(chat_id=111, message_id=12, text="On it.")
        clock.now = 3.0
        relay.pump()
        assert events == []
        clock.now = 4.0
        relay.pump()
        assert events == [AgentSpeakable(text="On it.", message_id=12)]
        clock.now = 5.0
        relay.pump()
        assert events[-1] == TurnSettled()

    async def test_own_outgoing_messages_are_ignored(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.send("first")
        await client.fire_new_message(chat_id=111, message_id=12, text="typed on phone", out=True)
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(e, AgentSpeakable) for e in events)

    async def test_messages_from_other_chats_are_ignored(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.send("first")
        await client.fire_new_message(chat_id=999, message_id=12, text="wrong chat")
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(e, AgentSpeakable) for e in events)

    async def test_switching_chats_rebinds_and_forgets_pending(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.send("first")
        await client.fire_new_message(chat_id=111, message_id=12, text="old chat reply")
        await relay.reset("ops")
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(e, AgentSpeakable) for e in events)
        await relay.send("in ops")
        assert client.sent[-1] == (client.entities[222], "in ops")

    async def test_unknown_chat_key_keeps_previous_binding(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")
        await relay.reset("bogus")
        await relay.send("still hermes")
        assert client.sent[-1][0] == client.entities["@hermes_bot"]

    async def test_close_stops_the_ticker(self) -> None:
        relay, _, _, _ = make_relay()
        await relay.reset("hermes")
        relay.close()
