import json
from pathlib import Path

from starlette.testclient import TestClient

from hermes_voice.server.app import create_app
from hermes_voice.server.config import ChatConfig, Config, TelegramConfig
from tests.io.test_telegram_relay import FakeClient
from tests.server.test_orchestrator_loop import FakeStt, FakeTts, FakeVad


def make_config() -> Config:
    return Config(
        token="",
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
            ws.send_text('{"type": "hello", "token": ""}')
            ready = json.loads(ws.receive_text())
        assert ready["type"] == "ready"
        assert ready["chats"] == [
            {"key": "hermes", "label": "Hermes"},
            {"key": "ops", "label": "Ops"},
        ]
        assert ready["active_chat"] == "hermes"

    def test_select_chat_is_accepted_without_error(self) -> None:
        with make_app() as client, client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            ws.send_text('{"type": "select_chat", "chat_key": "ops"}')
            ws.send_text('{"type": "cancel"}')


class TestTelegramTopicProtocol:
    def test_list_topics_returns_telegram_metadata(self) -> None:
        with make_app() as client, client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
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
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
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
