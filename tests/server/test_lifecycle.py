from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

import hermes_voice.server.app as app_module
from hermes_voice.server.app import create_app
from hermes_voice.server.config import ChatConfig, Config, TelegramConfig
from tests.server.test_orchestrator_loop import FakeVad


def make_config() -> Config:
    return Config(
        token="test-token-abcdefghijklmnopqrstuvwxyz0123456789",
        telegram=TelegramConfig(
            api_id=1,
            api_hash="hash",
            session_path=Path("/tmp/test.session"),
        ),
        chats={
            "hermes": ChatConfig(
                key="hermes",
                peer="@hermes_bot",
                label="Hermes",
                max_wait_s=180.0,
            )
        },
    )


class CloseTrackingPort:
    def __init__(self, *, fail_warmup: bool = False) -> None:
        self.fail_warmup = fail_warmup
        self.close_calls = 0

    async def warmup(self) -> None:
        if self.fail_warmup:
            raise RuntimeError("warmup failed")

    def close(self) -> None:
        self.close_calls += 1


class OwnedTelegramClient:
    def __init__(self) -> None:
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


class TestApplicationLifespanCleanup:
    def test_model_warmup_failure_closes_ports_and_owned_telegram(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = OwnedTelegramClient()
        stt = CloseTrackingPort(fail_warmup=True)
        tts = CloseTrackingPort()

        async def fake_connect(_config: Any) -> OwnedTelegramClient:
            return client

        monkeypatch.setattr(
            app_module,
            "_connect_telegram",
            fake_connect,
        )

        app = create_app(
            mode="telegram",
            config=make_config(),
            vad=FakeVad(),
            stt=stt,
            tts=tts,
        )

        with pytest.raises(RuntimeError, match="warmup failed"), TestClient(app):
            pass

        assert stt.close_calls == 1
        assert tts.close_calls == 1
        assert client.disconnect_calls == 1
