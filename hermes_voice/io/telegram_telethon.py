"""Telethon relay for Telegram chats and topics.

User transcripts are sent through the authenticated Telegram user session. Incoming
agent replies are filtered to the active chat and, when selected, the active topic
before they reach the ReplyAggregator.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from hermes_voice.kit import session as sm
from hermes_voice.kit.replies import ReplyAggregator, ReplyConfig, Settled, Speak
from hermes_voice.server.config import ChatConfig

logger = logging.getLogger(__name__)

TICK_INTERVAL_S = 0.25
MAX_TELEGRAM_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class TelegramTopic:
    topic_id: int
    title: str
    top_message_id: int | None
    closed: bool
    pinned: bool


@dataclass(frozen=True, slots=True)
class TelegramTopicMessage:
    message_id: int
    topic_id: int
    text: str
    is_outgoing: bool
    has_attachment: bool
    date: datetime | None


class TelegramRelay:
    def __init__(
        self,
        *,
        client: Any,
        chats: Mapping[str, ChatConfig],
        emit: Callable[[sm.Event], None],
        reply_config: ReplyConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._chats = chats
        self._emit = emit
        self._clock = clock
        self._aggregator = ReplyAggregator(reply_config or ReplyConfig())
        self._active_chat: ChatConfig | None = None
        self._active_peer_id: int | None = None
        self._active_topic_id: int | None = None
        self._entity: Any = None
        self._ticker: asyncio.Task[None] | None = None
        self._handlers_installed = False

    @property
    def active_topic_id(self) -> int | None:
        return self._active_topic_id

    async def reset(self, chat_key: str) -> None:
        chat = self._chats.get(chat_key)
        if chat is None:
            logger.warning("unknown chat key %r; keeping previous chat", chat_key)
            return
        from telethon import utils

        self._entity = await self._client.get_entity(chat.peer)
        self._active_peer_id = utils.get_peer_id(self._entity)
        self._active_chat = chat
        self._active_topic_id = None
        self._aggregator.reset()
        self._install_handlers()
        if self._ticker is None or self._ticker.done():
            self._ticker = asyncio.create_task(self._run_ticker())
        logger.info("voice session bound to chat %r (peer id %s)", chat_key, self._active_peer_id)

    async def select_topic(self, topic_id: int | None) -> None:
        if topic_id is not None and topic_id <= 0:
            raise ValueError("topic_id must be a positive integer or None")
        self._active_topic_id = topic_id
        self._aggregator.reset()
        logger.info(
            "voice session bound to topic %s",
            topic_id if topic_id is not None else "general",
        )

    async def list_topics(
        self,
        *,
        query: str = "",
        limit: int = MAX_TELEGRAM_PAGE_SIZE,
    ) -> tuple[TelegramTopic, ...]:
        _validate_limit(limit)
        entity = self._require_entity()

        from telethon.tl import functions

        input_peer = await self._client.get_input_entity(entity)
        result = await self._client(
            functions.messages.GetForumTopicsRequest(
                peer=input_peer,
                offset_date=None,
                offset_id=0,
                offset_topic=0,
                limit=limit,
                q=query.strip(),
            )
        )

        topics: list[TelegramTopic] = []
        for item in getattr(result, "topics", []):
            topic = _topic_from_telegram(item)
            if topic is not None:
                topics.append(topic)
        return tuple(topics)

    async def load_topic_history(
        self,
        topic_id: int,
        *,
        limit: int = 50,
    ) -> tuple[TelegramTopicMessage, ...]:
        if topic_id <= 0:
            raise ValueError("topic_id must be a positive integer")
        _validate_limit(limit)
        entity = self._require_entity()

        from telethon.tl import functions

        input_peer = await self._client.get_input_entity(entity)
        result = await self._client(
            functions.messages.GetRepliesRequest(
                peer=input_peer,
                msg_id=topic_id,
                offset_id=0,
                offset_date=0,
                add_offset=0,
                limit=limit,
                max_id=0,
                min_id=0,
                hash=0,
            )
        )

        messages: list[TelegramTopicMessage] = []
        for item in getattr(result, "messages", []):
            message = _topic_message_from_telegram(item, topic_id=topic_id)
            if message is not None:
                messages.append(message)

        messages.sort(key=lambda item: item.message_id)
        return tuple(messages)

    async def send(self, text: str) -> None:
        if self._entity is None:
            logger.error("no active chat; dropping message %r", text)
            return
        kwargs: dict[str, int] = {}
        if self._active_topic_id is not None:
            kwargs["reply_to"] = self._active_topic_id
        message = await self._client.send_message(self._entity, text, **kwargs)
        self._aggregator.anchor(message_id=message.id, now=self._clock())

    def close(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            self._ticker = None

    # --- Telethon event handlers ---

    def _install_handlers(self) -> None:
        if self._handlers_installed:
            return
        from telethon import events

        self._client.add_event_handler(self._on_new_message, events.NewMessage(incoming=True))
        self._client.add_event_handler(self._on_edited, events.MessageEdited())
        self._client.add_event_handler(self._on_user_update, events.UserUpdate())
        self._handlers_installed = True

    def _is_active_destination(self, chat_id: int | None, message: Any) -> bool:
        if self._active_peer_id is None or chat_id != self._active_peer_id:
            return False
        return _topic_id_for(message) == self._active_topic_id

    async def _on_new_message(self, event: Any) -> None:
        if not self._is_active_destination(event.chat_id, event.message) or event.message.out:
            return
        self._aggregator.on_agent_message(
            message_id=event.message.id, text=_speakable_text(event.message), now=self._clock()
        )

    async def _on_edited(self, event: Any) -> None:
        if not self._is_active_destination(event.chat_id, event.message) or event.message.out:
            return
        self._aggregator.on_agent_edit(
            message_id=event.message.id, text=_speakable_text(event.message), now=self._clock()
        )

    async def _on_user_update(self, event: Any) -> None:
        # Telegram typing updates identify the chat but do not reliably include a
        # topic/thread ID, so they are accepted at chat scope. Message delivery is
        # still strictly filtered to the active topic.
        if (
            self._active_peer_id is not None
            and event.chat_id == self._active_peer_id
            and getattr(event, "typing", False)
        ):
            self._aggregator.on_typing(now=self._clock())

    # --- aggregator pump ---

    def pump(self) -> None:
        for reply_event in self._aggregator.tick(now=self._clock()):
            match reply_event:
                case Speak(message_id=message_id, text=text):
                    self._emit(sm.AgentSpeakable(text=text, message_id=message_id))
                case Settled():
                    self._emit(sm.TurnSettled())

    async def _run_ticker(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL_S)
            self.pump()

    def _require_entity(self) -> Any:
        if self._entity is None:
            raise RuntimeError("no active Telegram chat selected")
        return self._entity


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_TELEGRAM_PAGE_SIZE:
        raise ValueError(
            f"limit must be between 1 and {MAX_TELEGRAM_PAGE_SIZE}, inclusive"
        )


def _topic_from_telegram(item: Any) -> TelegramTopic | None:
    topic_id = getattr(item, "id", None)
    title = getattr(item, "title", None)
    if not isinstance(topic_id, int) or not isinstance(title, str) or not title.strip():
        return None

    top_message_id = getattr(item, "top_message", None)
    if not isinstance(top_message_id, int):
        top_message_id = None

    return TelegramTopic(
        topic_id=topic_id,
        title=title.strip(),
        top_message_id=top_message_id,
        closed=bool(getattr(item, "closed", False)),
        pinned=bool(getattr(item, "pinned", False)),
    )


def _topic_message_from_telegram(
    item: Any,
    *,
    topic_id: int,
) -> TelegramTopicMessage | None:
    message_id = getattr(item, "id", None)
    if not isinstance(message_id, int):
        return None

    item_topic_id = _topic_id_for(item)
    if message_id != topic_id and item_topic_id != topic_id:
        return None

    raw_text = getattr(item, "message", None)
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    has_attachment = getattr(item, "media", None) is not None

    # Telegram can include blank service/action messages in topic history. They
    # contain no user-visible text or attachment, so omit them from conversation
    # history.
    if not text and not has_attachment:
        return None

    date = getattr(item, "date", None)
    if not isinstance(date, datetime):
        date = None

    return TelegramTopicMessage(
        message_id=message_id,
        topic_id=topic_id,
        text=text,
        is_outgoing=bool(getattr(item, "out", False)),
        has_attachment=has_attachment,
        date=date,
    )


def _topic_id_for(message: Any) -> int | None:
    reply = getattr(message, "reply_to", None)
    if reply is None:
        return None

    top_id = getattr(reply, "reply_to_top_id", None)
    if isinstance(top_id, int):
        return top_id

    # A direct reply to the topic root may carry only reply_to_msg_id plus the
    # forum_topic marker. This is the shape observed in private bot topics.
    if bool(getattr(reply, "forum_topic", False)):
        reply_id = getattr(reply, "reply_to_msg_id", None)
        if isinstance(reply_id, int):
            return reply_id

    return None


def _speakable_text(message: Any) -> str:
    text = (message.message or "").strip()
    if text:
        return text
    if message.media is not None:
        return "(sent an attachment)"
    return ""
