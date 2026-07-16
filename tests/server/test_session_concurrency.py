from __future__ import annotations

import json

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from hermes_voice.server.app import (
    VOICE_SESSION_BUSY_CLOSE_CODE,
    VOICE_SESSION_BUSY_MESSAGE,
    _VoiceSessionGate,
    create_app,
)
from tests.server.test_orchestrator_loop import FakeStt, FakeTts, FakeVad


class TestVoiceSessionGate:
    async def test_allows_one_owner_and_can_be_reused(self) -> None:
        gate = _VoiceSessionGate()

        assert await gate.acquire()
        assert not await gate.acquire()

        gate.release()

        assert await gate.acquire()
        gate.release()


class TestVoiceSessionConcurrency:
    def test_second_voice_session_is_rejected_until_first_closes(self) -> None:
        app = create_app(
            mode="parrot",
            vad=FakeVad(),
            stt=FakeStt(),
            tts=FakeTts(),
        )

        with TestClient(app) as client:
            with client.websocket_connect("/ws") as first:
                first.send_text('{"type": "hello", "token": ""}')
                assert json.loads(first.receive_text())["type"] == "ready"

                with client.websocket_connect("/ws") as second:
                    second.send_text('{"type": "hello", "token": ""}')
                    assert json.loads(second.receive_text()) == {
                        "type": "error",
                        "message": VOICE_SESSION_BUSY_MESSAGE,
                    }
                    try:
                        second.receive_text()
                    except WebSocketDisconnect as exc:
                        assert exc.code == VOICE_SESSION_BUSY_CLOSE_CODE
                    else:
                        raise AssertionError("busy voice session did not close")

            with client.websocket_connect("/ws") as replacement:
                replacement.send_text('{"type": "hello", "token": ""}')
                assert json.loads(replacement.receive_text())["type"] == "ready"

    def test_echo_sessions_are_not_serialized(self) -> None:
        app = create_app(mode="echo")

        with (
            TestClient(app) as client,
            client.websocket_connect("/ws") as first,
            client.websocket_connect("/ws") as second,
        ):
            first.send_text('{"type": "hello", "token": ""}')
            second.send_text('{"type": "hello", "token": ""}')

            assert json.loads(first.receive_text())["type"] == "ready"
            assert json.loads(second.receive_text())["type"] == "ready"
