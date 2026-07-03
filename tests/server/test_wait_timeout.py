"""When the agent never replies, the gateway speaks a notice and resumes listening."""

import json
from typing import Any

from starlette.testclient import TestClient

from hermes_voice.kit.ports import ResponderPort
from hermes_voice.server.app import create_app
from hermes_voice.server.orchestrator import OrchestratorConfig
from tests.server.test_orchestrator_loop import (
    SILENT_FRAME,
    SPEECH_FRAME,
    FakeStt,
    FakeTts,
    FakeVad,
)


class SilentResponder:
    """An agent that never answers."""

    def __init__(self, emit: Any) -> None:
        pass

    async def send(self, text: str) -> None:
        return None

    async def reset(self, chat_key: str) -> None:
        return None


def make_silent_responder(emit: Any) -> ResponderPort:
    return SilentResponder(emit)


class TestWaitTimeout:
    def test_timeout_speaks_notice_and_returns_to_listening(self) -> None:
        app = create_app(
            mode="parrot",
            vad=FakeVad(),
            stt=FakeStt("are you there"),
            tts=FakeTts(),
            make_responder=make_silent_responder,
            orchestrator_config=OrchestratorConfig(wait_timeout_s=0.1),
        )
        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            for _ in range(4):
                ws.send_bytes(SPEECH_FRAME)
            for _ in range(16):
                ws.send_bytes(SILENT_FRAME)

            controls: list[dict[str, Any]] = []
            audio = 0
            while True:
                message = ws.receive()
                if "bytes" in message:
                    audio += 1
                    continue
                control = json.loads(message["text"])
                controls.append(control)
                if control == {"type": "state", "name": "listening"}:
                    break

        states = [c["name"] for c in controls if c["type"] == "state"]
        assert states == ["transcribing", "waiting", "speaking", "listening"]
        assert any(c["type"] == "speak_start" for c in controls)
        assert audio >= 1  # the spoken "still waiting" notice
