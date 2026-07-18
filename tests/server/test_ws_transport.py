import json

import pytest
from starlette.testclient import TestClient

from hermes_voice.server.app import create_app


def make_client() -> TestClient:
    return TestClient(create_app(mode="echo"))


class TestWsHandshake:
    def test_hello_gets_ready_reply(self) -> None:
        with make_client().websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            reply = json.loads(ws.receive_text())
            assert reply["type"] == "ready"
            assert reply["chats"] == []

    def test_invalid_first_message_gets_error(self) -> None:
        with make_client().websocket_connect("/ws") as ws:
            ws.send_text("garbage")
            reply = json.loads(ws.receive_text())
            assert reply["type"] == "error"

    def test_binary_first_frame_gets_error(self) -> None:
        with make_client().websocket_connect("/ws") as ws:
            ws.send_bytes(b"not-a-hello")
            reply = json.loads(ws.receive_text())

            assert reply == {
                "type": "error",
                "message": ("expected a text hello as first message"),
            }

    def test_missing_hello_times_out(self) -> None:
        client = TestClient(
            create_app(
                mode="echo",
                hello_timeout_s=0.01,
            )
        )

        with client.websocket_connect("/ws") as ws:
            reply = json.loads(ws.receive_text())

            assert reply == {
                "type": "error",
                "message": "hello timeout",
            }


class TestEchoLoop:
    def test_binary_pcm_is_echoed_back_with_epoch_prefix(self) -> None:
        with make_client().websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            pcm = b"\x01\x02" * 512
            ws.send_bytes(pcm)
            frame = ws.receive_bytes()
            assert frame[:4] == (0).to_bytes(4, "little")
            assert frame[4:] == pcm


class TestStatic:
    def test_serves_index_html(self) -> None:
        response = make_client().get("/")
        assert response.status_code == 200
        assert "<html" in response.text.lower()


class TestAppValidation:
    @pytest.mark.parametrize(
        "mode",
        ["", "telegarm", "production"],
    )
    def test_invalid_mode_is_rejected(
        self,
        mode: str,
    ) -> None:
        with pytest.raises(
            ValueError,
            match="invalid Hermes Voice mode",
        ):
            create_app(mode=mode)

    @pytest.mark.parametrize(
        "timeout",
        [
            0,
            -1,
            float("nan"),
            float("inf"),
            True,
        ],
    )
    def test_invalid_hello_timeout_is_rejected(
        self,
        timeout: float,
    ) -> None:
        with pytest.raises(
            ValueError,
            match="hello_timeout_s",
        ):
            create_app(
                mode="echo",
                hello_timeout_s=timeout,
            )
