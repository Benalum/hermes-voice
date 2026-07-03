"""Full voice loop against the orchestrator with fake speech ports (no models)."""

import json
from typing import Any

from starlette.testclient import TestClient

from hermes_voice.server.app import create_app

SPEECH_FRAME = b"\x40\x00" * 512
SILENT_FRAME = b"\x00\x00" * 512


class FakeVad:
    def probability(self, frame: bytes) -> float:
        return 0.95 if frame == SPEECH_FRAME else 0.05


class FakeStt:
    def __init__(self, text: str = "hello agent") -> None:
        self.text = text
        self.utterances: list[bytes] = []

    async def transcribe(self, pcm: bytes) -> str:
        self.utterances.append(pcm)
        return self.text


class FakeTts:
    async def synthesize(self, text: str) -> bytes:
        return b"\x11\x22" * 240


def open_session(stt_text: str = "hello agent") -> tuple[TestClient, FakeStt]:
    stt = FakeStt(stt_text)
    app = create_app(mode="parrot", vad=FakeVad(), stt=stt, tts=FakeTts())
    client = TestClient(app)
    return client, stt


def drive_utterance(ws: Any) -> None:
    for _ in range(4):
        ws.send_bytes(SPEECH_FRAME)
    for _ in range(16):
        ws.send_bytes(SILENT_FRAME)


def collect_until_listening(ws: Any) -> tuple[list[dict[str, Any]], list[bytes]]:
    controls: list[dict[str, Any]] = []
    audio: list[bytes] = []
    while True:
        message = ws.receive()
        if "text" in message:
            control = json.loads(message["text"])
            controls.append(control)
            if control == {"type": "state", "name": "listening"}:
                return controls, audio
        else:
            audio.append(message["bytes"])


class TestParrotLoop:
    def test_spoken_utterance_is_transcribed_and_spoken_back(self) -> None:
        client, _ = open_session()
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()  # ready
            drive_utterance(ws)
            controls, audio = collect_until_listening(ws)

        transcript = next(c for c in controls if c["type"] == "transcript")
        assert transcript["text"] == "hello agent"
        assert transcript["role"] == "user"

        agent_text = next(c for c in controls if c["type"] == "agent_text")
        assert agent_text["text"] == "hello agent"

        speak_start = next(c for c in controls if c["type"] == "speak_start")
        assert speak_start["sample_rate"] == 24000

        assert len(audio) >= 1
        epoch = int.from_bytes(audio[0][:4], "little")
        assert epoch == speak_start["epoch"]
        assert audio[0][4:].startswith(b"\x11\x22")

        assert any(c == {"type": "speak_stop", "epoch": epoch} for c in controls)

    def test_utterance_pcm_reaches_stt_with_pre_roll(self) -> None:
        client, stt = open_session()
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            drive_utterance(ws)
            collect_until_listening(ws)
        assert len(stt.utterances) == 1
        assert len(stt.utterances[0]) == (4 + 16) * 1024

    def test_empty_transcript_returns_to_listening_without_reply(self) -> None:
        client, _ = open_session(stt_text="")
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            drive_utterance(ws)
            controls, audio = collect_until_listening(ws)
        assert not any(c["type"] in ("transcript", "agent_text", "speak_start") for c in controls)
        assert audio == []

    def test_state_progression_covers_full_loop(self) -> None:
        client, _ = open_session()
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            drive_utterance(ws)
            controls, _ = collect_until_listening(ws)
        states = [c["name"] for c in controls if c["type"] == "state"]
        assert states == ["transcribing", "waiting", "speaking", "listening"]
