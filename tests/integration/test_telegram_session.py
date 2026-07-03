"""Live Telethon checks against your own account. Requires a logged-in session
(run scripts/login.py first), then: pytest -m telegram"""

import time

import pytest

from hermes_voice.server.config import ChatConfig, ConfigError, load_config

pytestmark = pytest.mark.telegram


@pytest.fixture(scope="module")
def config():  # type: ignore[no-untyped-def]
    try:
        return load_config()
    except ConfigError as exc:
        pytest.skip(f"no config: {exc}")


class TestAuthorizedSession:
    async def test_session_is_authorized_and_chats_resolve(self, config) -> None:  # type: ignore[no-untyped-def]
        from telethon import TelegramClient

        client = TelegramClient(
            str(config.telegram.session_path),
            config.telegram.api_id,
            config.telegram.api_hash,
        )
        await client.connect()
        try:
            assert await client.is_user_authorized(), "run scripts/login.py first"
            for chat in config.chats.values():
                entity = await client.get_entity(chat.peer)
                assert entity is not None
        finally:
            await client.disconnect()

    async def test_relay_sends_to_saved_messages_and_filters_own_reply(self, config) -> None:  # type: ignore[no-untyped-def]
        """Saved Messages is a safe chat: we talk to ourselves. Our own outgoing
        message must be filtered (out=True), so nothing becomes speakable."""
        from telethon import TelegramClient

        from hermes_voice.io.telegram_telethon import TelegramRelay

        client = TelegramClient(
            str(config.telegram.session_path),
            config.telegram.api_id,
            config.telegram.api_hash,
        )
        await client.connect()
        try:
            events: list[object] = []
            chats = {"me": ChatConfig(key="me", peer="me", label="Saved", max_wait_s=30.0)}
            relay = TelegramRelay(client=client, chats=chats, emit=events.append)
            await relay.reset("me")
            marker = f"hermes-voice self-test {int(time.time())}"
            await relay.send(marker)

            import asyncio

            await asyncio.sleep(4.0)
            relay.pump()
            relay.close()
            assert events == []  # own message filtered; nothing speakable, no settle
        finally:
            await client.disconnect()
