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
from typing import Any

from hermes_voice.kit import session as sm
from hermes_voice.kit.replies import ReplyAggregator, ReplyConfig, Settled, Speak
from hermes_voice.server.config import ChatConfig

logger = logging.getLogger(__name__)

TICK_INTERVAL_S = 0.25


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
