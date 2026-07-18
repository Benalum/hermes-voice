from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from hermes_voice.server.app import (
    _connect_telegram,
    create_app,
)
from hermes_voice.server.config import ChatConfig, Config, TelegramConfig
from tests.io.test_telegram_relay import FakeClient
from tests.server.test_orchestrator_loop import FakeStt, FakeTts, FakeVad

TEST_TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz0123456789"


def make_config() -> Config:
    return Config(
        token=TEST_TOKEN,
        telegram=TelegramConfig(api_id=1, api_hash="h", session_path=Path("/tmp/x.session")),
        chats={
            "hermes": ChatConfig(key="hermes", peer="@hermes_bot", label="Hermes", max_wait_s=180),
            "ops": ChatConfig(key="ops", peer=222, label="Ops", max_wait_s=300),
        },
    )


def make_app() -> TestClient:
    app = create_app(
        mode="telegram",
        config=make_config(),
        telegram_client=FakeClient(),
        vad=FakeVad(),
        stt=FakeStt(),
        tts=FakeTts(),
    )
    return TestClient(app)


class TestTelegramMode:
    def test_ready_lists_configured_chats_with_first_active(self) -> None:
        with make_app() as client, client.websocket_connect("/ws") as ws:
            ws.send_text(
                '{"type": "hello", "token": "test-token-abcdefghijklmnopqrstuvwxyz0123456789"}'
            )
            ready = json.loads(ws.receive_text())
        assert ready["type"] == "ready"
        assert ready["chats"] == [
            {"key": "hermes", "label": "Hermes"},
            {"key": "ops", "label": "Ops"},
        ]
        assert ready["active_chat"] == "hermes"

    def test_select_chat_is_accepted_without_error(self) -> None:
        with make_app() as client, client.websocket_connect("/ws") as ws:
            ws.send_text(
                '{"type": "hello", "token": "test-token-abcdefghijklmnopqrstuvwxyz0123456789"}'
            )
            ws.receive_text()
            ws.send_text('{"type": "select_chat", "chat_key": "ops"}')
            ws.send_text('{"type": "cancel"}')

    def test_failed_chat_switch_does_not_close_websocket(self) -> None:
        telegram_client = FakeClient()
        del telegram_client.entities[222]
        app = create_app(
            mode="telegram",
            config=make_config(),
            telegram_client=telegram_client,
            vad=FakeVad(),
            stt=FakeStt(),
            tts=FakeTts(),
        )

        with TestClient(app) as client, client.websocket_connect("/ws") as ws:
            ws.send_text(
                '{"type": "hello", "token": "test-token-abcdefghijklmnopqrstuvwxyz0123456789"}'
            )
            ws.receive_text()
            ws.receive_text()

            ws.send_text('{"type": "select_chat", "chat_key": "ops"}')
            assert json.loads(ws.receive_text())["type"] == "error"

            ws.send_text('{"type": "list_chats", "limit": 500}')
            assert json.loads(ws.receive_text())["type"] == "chats"


class TestTelegramTopicProtocol:
    def test_list_topics_returns_telegram_metadata(self) -> None:
        with make_app() as client, client.websocket_connect("/ws") as ws:
            ws.send_text(
                '{"type": "hello", "token": "test-token-abcdefghijklmnopqrstuvwxyz0123456789"}'
            )
            ws.receive_text()
            assert json.loads(ws.receive_text()) == {
                "type": "mute_state",
                "on": False,
                "source": "session",
            }
            ws.send_text('{"type": "list_topics", "query": "system", "limit": 20}')
            reply = json.loads(ws.receive_text())

        assert reply == {
            "type": "topics",
            "topics": [
                {
                    "topic_id": 98,
                    "title": "System",
                    "top_message_id": 110,
                    "closed": False,
                    "pinned": False,
                }
            ],
        }

    def test_select_topic_returns_ack_and_chronological_history(self) -> None:
        with make_app() as client, client.websocket_connect("/ws") as ws:
            ws.send_text(
                '{"type": "hello", "token": "test-token-abcdefghijklmnopqrstuvwxyz0123456789"}'
            )
            ws.receive_text()
            assert json.loads(ws.receive_text()) == {
                "type": "mute_state",
                "on": False,
                "source": "session",
            }
            ws.send_text('{"type": "select_topic", "topic_id": 98, "history_limit": 20}')
            selected = json.loads(ws.receive_text())
            history = json.loads(ws.receive_text())

        assert selected == {"type": "topic_selected", "topic_id": 98}
        assert history["type"] == "topic_history"
        assert history["topic_id"] == 98
        assert [message["message_id"] for message in history["messages"]] == [108, 109, 110]
        assert [message["role"] for message in history["messages"]] == [
            "agent",
            "user",
            "agent",
        ]
        assert history["messages"][0]["has_attachment"] is True
        assert history["messages"][1]["date"] == "2026-07-12T04:00:00+00:00"


class TestTelegramStartupCleanup:
    async def test_unauthorized_client_is_disconnected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        created: list[FakeStartupClient] = []

        class FakeStartupClient:
            def __init__(
                self,
                _session: str,
                _api_id: int,
                _api_hash: str,
            ) -> None:
                self.disconnect_calls = 0
                created.append(self)

            async def connect(self) -> None:
                return None

            async def is_user_authorized(self) -> bool:
                return False

            async def disconnect(self) -> None:
                self.disconnect_calls += 1

        monkeypatch.setitem(
            sys.modules,
            "telethon",
            SimpleNamespace(
                TelegramClient=FakeStartupClient,
            ),
        )

        with pytest.raises(
            RuntimeError,
            match="no authorized Telegram session",
        ):
            await _connect_telegram(make_config())

        assert len(created) == 1
        assert created[0].disconnect_calls == 1

    async def test_cancelled_startup_is_disconnected_and_reraised(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        created: list[FakeCancelledClient] = []

        class FakeCancelledClient:
            def __init__(
                self,
                _session: str,
                _api_id: int,
                _api_hash: str,
            ) -> None:
                self.disconnect_calls = 0
                created.append(self)

            async def connect(self) -> None:
                return None

            async def is_user_authorized(self) -> bool:
                raise asyncio.CancelledError

            async def disconnect(self) -> None:
                self.disconnect_calls += 1

        monkeypatch.setitem(
            sys.modules,
            "telethon",
            SimpleNamespace(
                TelegramClient=FakeCancelledClient,
            ),
        )

        with pytest.raises(asyncio.CancelledError):
            await _connect_telegram(make_config())

        assert len(created) == 1
        assert created[0].disconnect_calls == 1
