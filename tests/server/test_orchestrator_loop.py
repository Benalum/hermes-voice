"""Full voice loop against the orchestrator with fake speech ports (no models)."""

import asyncio
import contextlib
import json
from typing import Any

import pytest
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

        assert any(c == {"type": "speak_stop", "epoch": epoch, "flush": False} for c in controls)

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

    def test_spoken_mute_suppresses_until_spoken_unmute(self) -> None:
        client, stt = open_session(stt_text="Mute me")
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()

            drive_utterance(ws)
            muted_controls, _ = collect_until_listening(ws)
            assert any(
                c == {"type": "mute_state", "on": True, "source": "voice"}
                for c in muted_controls
            )
            assert not any(c.get("role") == "user" for c in muted_controls)
            assert not any(c["type"] == "agent_text" for c in muted_controls)

            stt.text = "This private speech must not reach Telegram"
            drive_utterance(ws)
            private_controls, _ = collect_until_listening(ws)
            assert not any(c.get("role") == "user" for c in private_controls)
            assert not any(c["type"] == "agent_text" for c in private_controls)

            stt.text = "Start listening"
            drive_utterance(ws)
            unmuted_controls, _ = collect_until_listening(ws)
            assert any(
                c == {"type": "mute_state", "on": False, "source": "voice"}
                for c in unmuted_controls
            )

            stt.text = "Hello again"
            drive_utterance(ws)
            resumed_controls, _ = collect_until_listening(ws)
            assert any(
                c.get("type") == "transcript"
                and c.get("role") == "user"
                and c.get("text") == "Hello again"
                for c in resumed_controls
            )
            assert any(c["type"] == "agent_text" for c in resumed_controls)

    def test_button_mute_still_accepts_spoken_unmute(self) -> None:
        client, stt = open_session(stt_text="Private speech")
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()  # ready
            assert json.loads(ws.receive_text()) == {
                "type": "mute_state",
                "on": False,
                "source": "session",
            }

            ws.send_text('{"type": "mute", "on": true}')
            assert json.loads(ws.receive_text()) == {
                "type": "mute_state",
                "on": True,
                "source": "button",
            }

            drive_utterance(ws)
            private_controls, _ = collect_until_listening(ws)
            assert not any(c.get("role") == "user" for c in private_controls)
            assert not any(c["type"] == "agent_text" for c in private_controls)

            stt.text = "Unmute me"
            drive_utterance(ws)
            unmuted_controls, _ = collect_until_listening(ws)
            assert any(
                c == {"type": "mute_state", "on": False, "source": "voice"}
                for c in unmuted_controls
            )

            stt.text = "Hello after button mute"
            drive_utterance(ws)
            resumed_controls, _ = collect_until_listening(ws)
            assert any(
                c.get("role") == "user"
                and c.get("text") == "Hello after button mute"
                for c in resumed_controls
            )

    def test_state_progression_covers_full_loop(self) -> None:
        client, _ = open_session()
        with client.websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            ws.receive_text()
            drive_utterance(ws)
            controls, _ = collect_until_listening(ws)
        states = [c["name"] for c in controls if c["type"] == "state"]
        assert states == ["transcribing", "waiting", "speaking", "listening"]


class TestMutedPlayback:
    async def test_muted_speech_does_not_stop_active_playback(self) -> None:
        from hermes_voice.kit import session as sm
        from hermes_voice.server.orchestrator import Orchestrator

        sent: list[dict[str, Any]] = []
        stt = FakeStt("private speech")

        async def record_text(message: str) -> None:
            sent.append(json.loads(message))

        class LongTts:
            async def synthesize(self, text: str) -> bytes:
                return b"\x11\x22" * (24000 * 5)

        orchestrator = Orchestrator(
            send_text=record_text,
            send_bytes=_ignore_bytes,
            vad=FakeVad(),
            stt=stt,
            tts=LongTts(),
            make_responder=lambda emit: _IgnoreResponder(),
            initial_chat="hermes",
        )
        task = asyncio.create_task(orchestrator.run())
        try:
            await orchestrator.set_muted(True)
            orchestrator.emit(sm.AgentSpeakable(text="a long reply", message_id=1))
            for _ in range(100):
                if any(message["type"] == "speak_start" for message in sent):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("playback did not start")

            for frame in [SPEECH_FRAME] * 4 + [SILENT_FRAME] * 16:
                orchestrator.feed_audio(frame)
            for _ in range(100):
                if len(stt.utterances) == 1:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("muted utterance did not reach command-only STT")

            assert not any(
                message["type"] == "speak_stop" and message["flush"]
                for message in sent
            )

            stt.text = "Hermes unmute me"
            for frame in [SPEECH_FRAME] * 4 + [SILENT_FRAME] * 16:
                orchestrator.feed_audio(frame)
            for _ in range(100):
                if any(
                    message
                    == {"type": "mute_state", "on": False, "source": "voice"}
                    for message in sent
                ):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("spoken unmute was not accepted during playback")

            assert not any(
                message["type"] == "speak_stop" and message["flush"]
                for message in sent
            )
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


class TopicResponder:
    def __init__(self, emit: Any) -> None:
        self.emit = emit
        self.reset_calls: list[str] = []
        self.selected_topic: int | None = None

    async def reset(self, chat_key: str) -> None:
        self.reset_calls.append(chat_key)
        self.selected_topic = None

    async def send(self, text: str) -> None:
        return None

    async def list_topics(self, *, query: str, limit: int) -> tuple[str, ...]:
        return (f"{query}:{limit}",)

    async def select_topic(self, topic_id: int) -> None:
        self.selected_topic = topic_id

    async def load_topic_history(self, topic_id: int, *, limit: int) -> tuple[str, ...]:
        return (f"{topic_id}:{limit}",)

    async def close(self) -> None:
        return None


class TestOrchestratorTopicControls:
    async def test_topic_controls_wait_for_initial_reset_and_dispatch_chat_switch(self) -> None:
        from hermes_voice.kit import session as sm
        from hermes_voice.server.orchestrator import Orchestrator

        holder: dict[str, TopicResponder] = {}

        def make_responder(emit: Any) -> TopicResponder:
            responder = TopicResponder(emit)
            holder["responder"] = responder
            return responder

        orchestrator = Orchestrator(
            send_text=_ignore_text,
            send_bytes=_ignore_bytes,
            vad=FakeVad(),
            stt=FakeStt(),
            tts=FakeTts(),
            make_responder=make_responder,
            initial_chat="hermes",
        )
        task = asyncio.create_task(orchestrator.run())
        try:
            assert await orchestrator.list_topics(query="sys", limit=10) == ("sys:10",)
            await orchestrator.select_topic(98)
            assert holder["responder"].selected_topic == 98
            assert await orchestrator.load_topic_history(98, limit=20) == ("98:20",)
            await orchestrator.dispatch(sm.ChatSelected(chat_key="ops"))
            assert holder["responder"].reset_calls == ["hermes", "ops"]
            assert holder["responder"].selected_topic is None
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _ignore_text(_text: str) -> None:
    return None


async def _ignore_bytes(_data: bytes) -> None:
    return None


class FailingResetResponder:
    def __init__(self, _emit: Any) -> None:
        self.close_calls = 0

    async def reset(self, _chat_key: str) -> None:
        raise RuntimeError("reset failed")

    async def send(self, _text: str) -> None:
        return None

    async def close(self) -> None:
        self.close_calls += 1


class TestOrchestratorLifecycle:
    async def test_initial_reset_failure_closes_responder(self) -> None:
        from hermes_voice.server.orchestrator import Orchestrator

        holder: dict[str, FailingResetResponder] = {}

        def make_responder(emit: Any) -> FailingResetResponder:
            responder = FailingResetResponder(emit)
            holder["responder"] = responder
            return responder

        orchestrator = Orchestrator(
            send_text=_ignore_text,
            send_bytes=_ignore_bytes,
            vad=FakeVad(),
            stt=FakeStt(),
            tts=FakeTts(),
            make_responder=make_responder,
            initial_chat="hermes",
        )

        with pytest.raises(RuntimeError, match="reset failed"):
            await orchestrator.run()

        assert holder["responder"].close_calls == 1

    def test_websocket_reports_orchestrator_startup_failure(self) -> None:
        app = create_app(
            mode="parrot",
            vad=FakeVad(),
            stt=FakeStt(),
            tts=FakeTts(),
            make_responder=FailingResetResponder,
        )

        with TestClient(app).websocket_connect("/ws") as ws:
            ws.send_text('{"type": "hello", "token": ""}')
            assert json.loads(ws.receive_text())["type"] == "ready"
            assert json.loads(ws.receive_text()) == {
                "type": "error",
                "message": "voice session failed",
            }


class _RecordingStt:
    def __init__(self) -> None:
        self.calls = 0

    async def transcribe(self, pcm: bytes) -> str:
        self.calls += 1
        return "should never happen"


class TestSpeakerGateIntegration:
    async def test_rejected_utterance_never_reaches_stt(self, tmp_path) -> None:
        import numpy as np
        from hermes_voice.kit import session as sm
        from hermes_voice.kit.speaker_gate import SpeakerGate, SpeakerGateConfig
        from hermes_voice.server.orchestrator import Orchestrator

        # Real gate; verify() is monkeypatched to always reject.
        gate = SpeakerGate(
            SpeakerGateConfig(enabled=True, threshold=0.75, store=tmp_path / "sp.json")
        )
        gate.enroll("alex", np.zeros(256, dtype=np.float32))  # make is_configured True
        gate.verify = lambda emb: (False, 0.1, None)  # type: ignore[method-assign]
        gate.embed = staticmethod(lambda pcm: np.zeros(256, dtype=np.float32))  # type: ignore[method-assign]

        stt = _RecordingStt()

        orchestrator = Orchestrator(
            send_text=_ignore_text,
            send_bytes=_ignore_bytes,
            vad=FakeVad(),
            stt=stt,
            tts=FakeTts(),
            make_responder=lambda e: _IgnoreResponder(),
            initial_chat="hermes",
            speaker_gate=gate,
        )
        task = asyncio.create_task(orchestrator.run())
        try:
            # Simulate a completed utterance arriving from VAD.
            await orchestrator.dispatch(sm.SpeechEnded(pcm=b"\x01\x00" * 8000))
            # Give the transcribe coroutine time to run (and be rejected).
            for _ in range(20):
                await asyncio.sleep(0.01)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        assert stt.calls == 0, "STT must not be called for a rejected speaker"


class _IgnoreResponder:
    async def reset(self, chat_key: str) -> None:
        return None

    async def send(self, text: str) -> None:
        return None

    def list_topics(self, *, query: str = "", limit: int = 100):
        return ()

    async def select_topic(self, topic_id: int) -> None:
        return None

    async def load_topic_history(self, topic_id: int, *, limit: int = 50):
        return ()
