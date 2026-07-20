from __future__ import annotations

import io
import json
import wave
from unittest.mock import patch

import httpx
import pytest

from hermes_voice.io.remote_speech import RemoteSpeechError, RemoteSpeechPorts

TOKEN = "a" * 64


def wav_bytes(pcm: bytes, *, sample_rate: int = 24_000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


def build_remote(handler: httpx.MockTransport) -> RemoteSpeechPorts:
    return RemoteSpeechPorts(
        base_url="http://speech:9000",
        client_id="hermes1",
        token=TOKEN,
        timeout_seconds=10,
        async_transport=handler,
        sync_transport=handler,
    )


@pytest.mark.asyncio
async def test_remote_ports_use_authenticated_api_contract() -> None:
    seen_paths: list[str] = []
    pcm = b"\x01\x00\x02\x00"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert request.headers["x-client-id"] == "hermes1"
        seen_paths.append(request.url.path)
        if request.url.path == "/readyz":
            return httpx.Response(200, json={"status": "ready"})
        assert request.headers["x-request-id"]
        if request.url.path == "/v1/vad":
            assert request.headers["x-audio-sample-rate"] == "16000"
            assert request.content == pcm
            return httpx.Response(200, json={"speech_probability": 0.75})
        if request.url.path == "/v1/stt":
            assert request.content == pcm
            return httpx.Response(200, json={"text": "  shared speech works  "})
        if request.url.path == "/v1/speaker/verify":
            assert request.content == pcm
            return httpx.Response(
                200,
                json={
                    "configured": True,
                    "accepted": True,
                    "score": 0.91,
                    "speaker": "alex",
                    "threshold": 0.75,
                    "reason": "accepted",
                },
            )
        if request.url.path == "/v1/tts":
            assert request.read() == b'{"text":"Hello","speed":1.0}'
            return httpx.Response(
                200,
                content=wav_bytes(pcm),
                headers={"Content-Type": "audio/wav"},
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    remote = build_remote(httpx.MockTransport(handler))
    try:
        await remote.warmup()
        await remote.warmup()
        assert remote.probability(pcm) == 0.75
        decision = await remote.verify_speaker(pcm)
        assert decision.configured is True
        assert decision.accepted is True
        assert decision.score == 0.91
        assert decision.speaker == "alex"
        assert await remote.transcribe(pcm) == "shared speech works"
        assert await remote.synthesize("Hello") == pcm
    finally:
        await remote.close()
        await remote.close()

    assert seen_paths == [
        "/readyz",
        "/v1/vad",
        "/v1/speaker/verify",
        "/v1/stt",
        "/v1/tts",
    ]


@pytest.mark.asyncio
async def test_remote_tts_speed_can_change() -> None:
    seen_speeds: list[float] = []
    pcm = b"\x01\x00"

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read())
        seen_speeds.append(float(payload["speed"]))
        return httpx.Response(200, content=wav_bytes(pcm))

    remote = build_remote(httpx.MockTransport(handler))
    try:
        assert await remote.synthesize("default") == pcm
        remote.set_speed(1.35)
        assert await remote.synthesize("faster") == pcm
        with pytest.raises(ValueError, match=r"between 0\.5 and 2\.0"):
            remote.set_speed(2.5)
    finally:
        await remote.close()

    assert seen_speeds == [1.0, 1.35]


@pytest.mark.asyncio
async def test_remote_speaker_decision_is_strictly_validated() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "configured": True,
                "accepted": "yes",
                "score": 0.91,
                "speaker": "alex",
                "threshold": 0.75,
                "reason": "accepted",
            },
        )

    remote = build_remote(httpx.MockTransport(handler))
    try:
        with pytest.raises(RemoteSpeechError, match="invalid speaker decision"):
            await remote.verify_speaker(b"\0\0")
    finally:
        await remote.close()


@pytest.mark.asyncio
async def test_remote_error_does_not_expose_token() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid client credentials"})

    remote = build_remote(httpx.MockTransport(handler))
    try:
        with pytest.raises(RemoteSpeechError, match="invalid client credentials") as failure:
            await remote.transcribe(b"\0\0")
    finally:
        await remote.close()

    assert TOKEN not in str(failure.value)


@pytest.mark.asyncio
async def test_tts_rejects_wrong_audio_format() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=wav_bytes(b"\0\0", sample_rate=16_000))

    remote = build_remote(httpx.MockTransport(handler))
    try:
        with pytest.raises(RemoteSpeechError, match="mono 24 kHz"):
            await remote.synthesize("Hello")
    finally:
        await remote.close()


def test_remote_settings_are_loaded_from_environment() -> None:
    environment = {
        "HV_SPEECH_SERVICE_URL": "http://192.168.0.201:9000/",
        "HV_SPEECH_CLIENT_ID": "hermes1",
        "HV_SPEECH_SERVICE_TOKEN": TOKEN,
        "HV_SPEECH_REQUEST_TIMEOUT_SECONDS": "30",
    }
    with (
        patch.dict("os.environ", environment, clear=True),
        patch("hermes_voice.io.remote_speech.httpx.AsyncClient") as async_client,
        patch("hermes_voice.io.remote_speech.httpx.Client"),
    ):
        remote = RemoteSpeechPorts.from_env()

    assert remote._closed is False
    assert async_client.call_args.kwargs["base_url"] == "http://192.168.0.201:9000"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("HV_SPEECH_SERVICE_URL", "ftp://speech", "http or https"),
        ("HV_SPEECH_CLIENT_ID", "", "non-empty"),
        ("HV_SPEECH_SERVICE_TOKEN", "short", "at least 32 bytes"),
        ("HV_SPEECH_REQUEST_TIMEOUT_SECONDS", "0", "between 0 and 900"),
        ("HV_KOKORO_SPEED", "3", "between 0.5 and 2.0"),
    ],
)
def test_invalid_remote_settings_are_rejected(name: str, value: str, message: str) -> None:
    environment = {
        "HV_SPEECH_SERVICE_URL": "http://speech:9000",
        "HV_SPEECH_CLIENT_ID": "hermes1",
        "HV_SPEECH_SERVICE_TOKEN": TOKEN,
        "HV_SPEECH_REQUEST_TIMEOUT_SECONDS": "30",
    }
    environment[name] = value
    with (
        patch.dict("os.environ", environment, clear=True),
        pytest.raises(ValueError, match=message),
    ):
        RemoteSpeechPorts.from_env()
