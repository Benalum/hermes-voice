"""Relay wiring tests with a fake Telethon client - no network, no session."""

from types import SimpleNamespace
from typing import Any

import pytest
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
        self.sent: list[tuple[Any, str, int | None]] = []
        self.entities = {"@hermes_bot": types.User(id=111), 222: types.User(id=222)}
        self.next_message_id = 10

    def add_event_handler(self, callback: Any, event_filter: Any) -> None:
        self.handlers.append((callback, type(event_filter).__name__))

    async def get_entity(self, peer: Any) -> Any:
        return self.entities[peer]

    async def send_message(
        self,
        entity: Any,
        text: str,
        *,
        reply_to: int | None = None,
    ) -> Any:
        self.sent.append((entity, text, reply_to))
        self.next_message_id += 1
        return SimpleNamespace(id=self.next_message_id)

    async def fire_new_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        out: bool = False,
        topic_id: int | None = None,
        direct_to_topic_root: bool = False,
    ) -> None:
        reply_to = None
        if topic_id is not None:
            if direct_to_topic_root:
                reply_to = SimpleNamespace(
                    reply_to_top_id=None,
                    reply_to_msg_id=topic_id,
                    forum_topic=True,
                )
            else:
                reply_to = SimpleNamespace(
                    reply_to_top_id=topic_id,
                    reply_to_msg_id=message_id - 1,
                    forum_topic=True,
                )
        event = SimpleNamespace(
            chat_id=chat_id,
            message=SimpleNamespace(
                id=message_id,
                out=out,
                message=text,
                media=None,
                reply_to=reply_to,
            ),
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
    async def test_send_posts_into_the_active_chat_general_stream(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")
        await relay.send("do the thing")
        assert client.sent == [(client.entities["@hermes_bot"], "do the thing", None)]

    async def test_send_posts_into_the_selected_topic(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("do the thing")
        assert client.sent == [(client.entities["@hermes_bot"], "do the thing", 98)]
        assert relay.active_topic_id == 98

    async def test_select_topic_rejects_non_positive_ids(self) -> None:
        relay, _, _, _ = make_relay()
        await relay.reset("hermes")
        with pytest.raises(ValueError):
            await relay.select_topic(0)

    async def test_agent_reply_in_selected_topic_becomes_speakable_then_settles(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        clock.now = 1.0
        await relay.send("do the thing")
        clock.now = 2.0
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="On it.",
            topic_id=98,
        )
        clock.now = 3.0
        relay.pump()
        assert events == []
        clock.now = 4.0
        relay.pump()
        assert events == [AgentSpeakable(text="On it.", message_id=12)]
        clock.now = 5.0
        relay.pump()
        assert events[-1] == TurnSettled()

    async def test_direct_reply_to_topic_root_is_accepted(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("first")
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="root reply",
            topic_id=98,
            direct_to_topic_root=True,
        )
        clock.now = 100.0
        relay.pump()
        assert any(isinstance(event, AgentSpeakable) for event in events)

    async def test_message_from_other_topic_is_ignored(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("first")
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="wrong topic",
            topic_id=105,
        )
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(event, AgentSpeakable) for event in events)

    async def test_general_stream_ignores_topic_messages(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.send("first")
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="topic reply",
            topic_id=98,
        )
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(event, AgentSpeakable) for event in events)

    async def test_own_outgoing_messages_are_ignored(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("first")
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="typed on phone",
            out=True,
            topic_id=98,
        )
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(event, AgentSpeakable) for event in events)

    async def test_messages_from_other_chats_are_ignored(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("first")
        await client.fire_new_message(
            chat_id=999,
            message_id=12,
            text="wrong chat",
            topic_id=98,
        )
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(event, AgentSpeakable) for event in events)

    async def test_switching_chats_clears_topic_and_forgets_pending(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("first")
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="old chat reply",
            topic_id=98,
        )
        await relay.reset("ops")
        assert relay.active_topic_id is None
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(event, AgentSpeakable) for event in events)
        await relay.send("in ops")
        assert client.sent[-1] == (client.entities[222], "in ops", None)

    async def test_switching_topics_forgets_pending_reply(self) -> None:
        relay, client, clock, events = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.send("first")
        await client.fire_new_message(
            chat_id=111,
            message_id=12,
            text="old topic reply",
            topic_id=98,
        )
        await relay.select_topic(105)
        clock.now = 100.0
        relay.pump()
        assert not any(isinstance(event, AgentSpeakable) for event in events)

    async def test_unknown_chat_key_keeps_previous_binding(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(98)
        await relay.reset("bogus")
        await relay.send("still hermes")
        assert client.sent[-1] == (client.entities["@hermes_bot"], "still hermes", 98)

    async def test_close_stops_the_ticker(self) -> None:
        relay, _, _, _ = make_relay()
        await relay.reset("hermes")
        relay.close()
