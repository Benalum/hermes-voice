"""Telethon relay: sends user transcripts into the active chat as Stephen's own
account and feeds agent replies/edits/typing into the ReplyAggregator, which
decides what to speak and when the turn settles."""

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
        self._entity: Any = None
        self._ticker: asyncio.Task[None] | None = None
        self._handlers_installed = False

    async def reset(self, chat_key: str) -> None:
        chat = self._chats.get(chat_key)
        if chat is None:
            logger.warning("unknown chat key %r; keeping previous chat", chat_key)
            return
        from telethon import utils

        self._entity = await self._client.get_entity(chat.peer)
        self._active_peer_id = utils.get_peer_id(self._entity)
        self._active_chat = chat
        self._aggregator.reset()
        self._install_handlers()
        if self._ticker is None or self._ticker.done():
            self._ticker = asyncio.create_task(self._run_ticker())
        logger.info("voice session bound to chat %r (peer id %s)", chat_key, self._active_peer_id)

    async def send(self, text: str) -> None:
        if self._entity is None:
            logger.error("no active chat; dropping message %r", text)
            return
        message = await self._client.send_message(self._entity, text)
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

    def _is_active_chat(self, chat_id: int | None) -> bool:
        return self._active_peer_id is not None and chat_id == self._active_peer_id

    async def _on_new_message(self, event: Any) -> None:
        if not self._is_active_chat(event.chat_id) or event.message.out:
            return
        self._aggregator.on_agent_message(
            message_id=event.message.id, text=_speakable_text(event.message), now=self._clock()
        )

    async def _on_edited(self, event: Any) -> None:
        if not self._is_active_chat(event.chat_id) or event.message.out:
            return
        self._aggregator.on_agent_edit(
            message_id=event.message.id, text=_speakable_text(event.message), now=self._clock()
        )

    async def _on_user_update(self, event: Any) -> None:
        if self._is_active_chat(event.chat_id) and getattr(event, "typing", False):
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


def _speakable_text(message: Any) -> str:
    text = (message.message or "").strip()
    if text:
        return text
    if message.media is not None:
        return "(sent an attachment)"
    return ""
