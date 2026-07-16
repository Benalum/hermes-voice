import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from hermes_voice.server.app import create_app
from hermes_voice.server.config import (
    ChatConfig,
    Config,
    ConfigError,
    TelegramConfig,
)
from tests.io.test_telegram_relay import FakeClient
from tests.server.test_orchestrator_loop import FakeStt, FakeTts, FakeVad


def make_app(token: str) -> TestClient:
    config = Config(
        token=token,
        telegram=TelegramConfig(api_id=1, api_hash="h", session_path=Path("/tmp/x.session")),
        chats={
            "hermes": ChatConfig(key="hermes", peer="@hermes_bot", label="Hermes", max_wait_s=180)
        },
    )
    app = create_app(
        mode="telegram",
        config=config,
        telegram_client=FakeClient(),
        vad=FakeVad(),
        stt=FakeStt(),
        tts=FakeTts(),
    )
    return TestClient(app)


TEST_TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz0123456789"


class TestTokenAuth:
    def test_wrong_token_gets_error_and_close(self) -> None:
        with make_app(TEST_TOKEN) as client, client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": "wrong"}')
            reply = json.loads(ws.receive_text())
            assert reply["type"] == "error"
            assert "token" in reply["message"]

    def test_correct_token_gets_ready(self) -> None:
        with make_app(TEST_TOKEN) as client, client.websocket_connect("/ws") as ws:
            ws.send_text(
                '{"type": "hello", "token": "test-token-abcdefghijklmnopqrstuvwxyz0123456789"}'
            )
            assert json.loads(ws.receive_text())["type"] == "ready"

    @pytest.mark.parametrize(
        "token",
        ["", "   ", "change-me", "too-short"],
    )
    def test_invalid_configured_token_is_rejected_at_app_creation(
        self,
        token: str,
    ) -> None:
        with pytest.raises(ConfigError, match="token"):
            make_app(token)
