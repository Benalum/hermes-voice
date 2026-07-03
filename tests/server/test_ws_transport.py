import json

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
