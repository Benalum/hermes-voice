"""Relay wiring tests with a fake Telethon client - no network, no session."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from telethon.tl import types

from hermes_voice.io.telegram_telethon import (
    TelegramRelay,
    TelegramTopic,
    TelegramTopicMessage,
)
from hermes_voice.kit.replies import ReplyConfig
from hermes_voice.kit.session import AgentSpeakable, Event, TurnSettled
from hermes_voice.server.config import ChatConfig

CHATS = {
    "hermes": ChatConfig(key="hermes", peer="@hermes_bot", label="Hermes", max_wait_s=180.0),
    "ops": ChatConfig(key="ops", peer=222, label="Ops", max_wait_s=300.0),
}


class FakeClient:
    def __init__(self) -> None:
        self.handlers: list[tuple[Any, Any]] = []
        self.sent: list[tuple[Any, str, int | None]] = []
        self.entities = {
            "@hermes_bot": types.User(id=111),
            222: types.User(id=222),
            333: SimpleNamespace(id=333),
            444: SimpleNamespace(id=444),
        }
        self.next_message_id = 10
        self.requests: list[Any] = []
        self.dialog_limits: list[int] = []
        self.dialogs = [
            SimpleNamespace(
                id=111,
                name="Hermes",
                entity=SimpleNamespace(id=111),
                is_user=True,
                is_group=False,
                is_channel=False,
            ),
            SimpleNamespace(
                id=333,
                name="Family Group",
                entity=SimpleNamespace(id=333),
                is_user=False,
                is_group=True,
                is_channel=False,
            ),
            SimpleNamespace(
                id=444,
                name="News Channel",
                entity=SimpleNamespace(id=444),
                is_user=False,
                is_group=False,
                is_channel=True,
            ),
        ]
        self.topics = [
            SimpleNamespace(
                id=105,
                title="Latest Topic",
                top_message=130,
                closed=False,
                pinned=True,
            ),
            SimpleNamespace(
                id=98,
                title="System",
                top_message=110,
                closed=False,
                pinned=False,
            ),
        ]
        topic_reply = SimpleNamespace(
            reply_to_top_id=98,
            reply_to_msg_id=98,
            forum_topic=True,
        )
        other_topic_reply = SimpleNamespace(
            reply_to_top_id=105,
            reply_to_msg_id=105,
            forum_topic=True,
        )
        self.topic_messages = {
            98: [
                SimpleNamespace(
                    id=110,
                    out=False,
                    message="Hermes reply",
                    media=None,
                    reply_to=topic_reply,
                    date=datetime(2026, 7, 12, 4, 1, tzinfo=UTC),
                ),
                SimpleNamespace(
                    id=109,
                    out=True,
                    message="User prompt",
                    media=None,
                    reply_to=topic_reply,
                    date=datetime(2026, 7, 12, 4, 0, tzinfo=UTC),
                ),
                SimpleNamespace(
                    id=108,
                    out=False,
                    message="diagram",
                    media=SimpleNamespace(kind="photo"),
                    reply_to=topic_reply,
                    date=datetime(2026, 7, 12, 3, 59, tzinfo=UTC),
                ),
                SimpleNamespace(
                    id=107,
                    out=False,
                    message="",
                    media=None,
                    reply_to=topic_reply,
                    date=datetime(2026, 7, 12, 3, 58, 30, tzinfo=UTC),
                ),
                SimpleNamespace(
                    id=98,
                    out=False,
                    message="",
                    media=None,
                    reply_to=topic_reply,
                    date=datetime(2026, 7, 12, 3, 58, tzinfo=UTC),
                ),
                SimpleNamespace(
                    id=120,
                    out=False,
                    message="wrong topic",
                    media=None,
                    reply_to=other_topic_reply,
                    date=datetime(2026, 7, 12, 4, 2, tzinfo=UTC),
                ),
            ]
        }

    def add_event_handler(self, callback: Any, event_filter: Any) -> None:
        self.handlers.append((callback, event_filter))

    def remove_event_handler(self, callback: Any, event_filter: Any = None) -> int:
        before = len(self.handlers)
        self.handlers = [
            (registered_callback, registered_filter)
            for registered_callback, registered_filter in self.handlers
            if not (
                registered_callback == callback
                and (event_filter is None or registered_filter is event_filter)
            )
        ]
        return before - len(self.handlers)

    async def get_entity(self, peer: Any) -> Any:
        return self.entities[peer]

    async def get_dialogs(self, *, limit: int = 100, **_kwargs: Any) -> list[Any]:
        self.dialog_limits.append(limit)
        # Real Telethon returns a TotalList (a list-like collection), not an
        # object with a `.dialogs` attribute.
        return self.dialogs[:limit]

    async def get_input_entity(self, entity: Any) -> Any:
        return SimpleNamespace(entity=entity)

    async def __call__(self, request: Any) -> Any:
        self.requests.append(request)
        request_name = type(request).__name__

        if request_name == "GetForumTopicsRequest":
            query = request.q.casefold()
            topics = [
                topic for topic in self.topics if not query or query in topic.title.casefold()
            ]
            return SimpleNamespace(topics=topics[: request.limit])

        if request_name == "GetRepliesRequest":
            messages = self.topic_messages.get(request.msg_id, [])
            return SimpleNamespace(messages=messages[: request.limit])

        raise AssertionError(f"unexpected Telegram request: {request_name}")

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
        for callback, event_filter in tuple(self.handlers):
            if type(event_filter).__name__ == "NewMessage":
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
    async def test_list_topics_preserves_telegram_order_and_metadata(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")

        topics = await relay.list_topics(limit=25)

        assert topics == (
            TelegramTopic(
                topic_id=105,
                title="Latest Topic",
                top_message_id=130,
                closed=False,
                pinned=True,
            ),
            TelegramTopic(
                topic_id=98,
                title="System",
                top_message_id=110,
                closed=False,
                pinned=False,
            ),
        )
        request = client.requests[-1]
        assert type(request).__name__ == "GetForumTopicsRequest"
        assert request.limit == 25
        assert request.q == ""

    async def test_list_topics_passes_trimmed_search_to_telegram(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")

        topics = await relay.list_topics(query="  system  ")

        assert [topic.title for topic in topics] == ["System"]
        assert client.requests[-1].q == "system"

    async def test_topic_reads_require_active_chat_and_valid_limits(self) -> None:
        relay, _, _, _ = make_relay()

        with pytest.raises(RuntimeError, match="no active Telegram chat"):
            await relay.list_topics()
        with pytest.raises(ValueError, match="between 1 and 100"):
            await relay.list_topics(limit=0)

        await relay.reset("hermes")
        with pytest.raises(ValueError, match="positive integer"):
            await relay.load_topic_history(0)
        with pytest.raises(ValueError, match="between 1 and 100"):
            await relay.load_topic_history(98, limit=101)

    async def test_load_topic_history_returns_chronological_conversation(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")

        messages = await relay.load_topic_history(98, limit=50)

        assert messages == (
            TelegramTopicMessage(
                message_id=108,
                topic_id=98,
                text="diagram",
                is_outgoing=False,
                has_attachment=True,
                date=datetime(2026, 7, 12, 3, 59, tzinfo=UTC),
            ),
            TelegramTopicMessage(
                message_id=109,
                topic_id=98,
                text="User prompt",
                is_outgoing=True,
                has_attachment=False,
                date=datetime(2026, 7, 12, 4, 0, tzinfo=UTC),
            ),
            TelegramTopicMessage(
                message_id=110,
                topic_id=98,
                text="Hermes reply",
                is_outgoing=False,
                has_attachment=False,
                date=datetime(2026, 7, 12, 4, 1, tzinfo=UTC),
            ),
        )
        request = client.requests[-1]
        assert type(request).__name__ == "GetRepliesRequest"
        assert request.msg_id == 98
        assert request.limit == 50

    async def test_load_topic_history_does_not_change_active_topic(self) -> None:
        relay, _, _, _ = make_relay()
        await relay.reset("hermes")
        await relay.select_topic(105)

        await relay.load_topic_history(98)

        assert relay.active_topic_id == 105

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

    async def test_close_stops_ticker_and_removes_handlers(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")
        ticker = relay._ticker

        assert len(client.handlers) == 3
        assert ticker is not None

        await relay.close()

        assert client.handlers == []
        assert relay._ticker is None
        assert ticker.done()

        await relay.close()
        assert client.handlers == []

    async def test_repeated_sessions_restore_handler_count_to_baseline(self) -> None:
        client = FakeClient()

        for _ in range(3):
            relay = TelegramRelay(
                client=client,
                chats=CHATS,
                emit=lambda _event: None,
            )
            await relay.reset("hermes")
            assert len(client.handlers) == 3
            await relay.close()
            assert client.handlers == []


class TestTelegramRelayChatDiscovery:
    async def test_list_chats_accepts_telethon_total_list_shape(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")

        chats = await relay.list_chats(limit=500)
        keys = {item.key for item in chats}

        assert {"hermes", "ops", "111", "333", "444"} <= keys
        assert client.dialog_limits == [498]

    async def test_list_chats_filters_case_insensitively(self) -> None:
        relay, _, _, _ = make_relay()
        await relay.reset("hermes")

        chats = await relay.list_chats(query="family", limit=500)

        assert [item.label for item in chats if item.kind != "config"] == ["Family Group"]

    async def test_discovered_dialog_can_become_the_active_destination(self) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")

        await relay.reset("333")
        await relay.send("hi family")

        assert relay._active_peer_id == 333
        assert client.sent[-1][0].id == 333


class TestTelegramRelayCleanupFailures:
    async def test_failed_ticker_does_not_prevent_handler_removal(
        self,
    ) -> None:
        relay, client, _, _ = make_relay()
        await relay.reset("hermes")

        original_ticker = relay._ticker
        assert original_ticker is not None

        original_ticker.cancel()
        await asyncio.gather(
            original_ticker,
            return_exceptions=True,
        )

        async def failing_ticker() -> None:
            raise RuntimeError("ticker failure")

        failed_ticker = asyncio.create_task(failing_ticker())
        await asyncio.sleep(0)

        assert failed_ticker.done()
        relay._ticker = failed_ticker

        await relay.close()

        assert client.handlers == []
        assert relay._ticker is None
