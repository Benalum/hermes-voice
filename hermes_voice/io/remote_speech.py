"""Remote STT, TTS, and VAD adapters for a shared Hermes Speech service."""

from __future__ import annotations

import asyncio
import io
import math
import os
import uuid
import wave
from typing import Any
from urllib.parse import urlsplit

import httpx

from hermes_voice.kit.ports import SpeakerDecision

STT_SAMPLE_RATE = 16_000
TTS_SAMPLE_RATE = 24_000
DEFAULT_TIMEOUT_SECONDS = 180.0


class RemoteSpeechError(RuntimeError):
    """A shared-speech request failed or returned an invalid payload."""


def _required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty value without surrounding whitespace")
    return value


def _service_url() -> str:
    value = _required_env("HV_SPEECH_SERVICE_URL").rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("HV_SPEECH_SERVICE_URL must be an absolute http or https URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("HV_SPEECH_SERVICE_URL must not contain credentials")
    return value


def _timeout_seconds() -> float:
    raw = os.environ.get(
        "HV_SPEECH_REQUEST_TIMEOUT_SECONDS",
        str(DEFAULT_TIMEOUT_SECONDS),
    )
    try:
        resolved = float(raw)
    except ValueError as exc:
        raise ValueError("HV_SPEECH_REQUEST_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(resolved) or resolved <= 0 or resolved > 900:
        raise ValueError(
            "HV_SPEECH_REQUEST_TIMEOUT_SECONDS must be a finite number between 0 and 900"
        )
    return resolved


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "speech request failed"
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
    return "speech request failed"


def _json_object(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise RemoteSpeechError(f"Hermes Speech returned invalid {operation} JSON") from exc
    if not isinstance(body, dict):
        raise RemoteSpeechError(f"Hermes Speech returned invalid {operation} JSON")
    return body


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RemoteSpeechError(
            f"Hermes Speech returned HTTP {response.status_code}: {_response_detail(response)}"
        ) from exc


def _request_headers() -> dict[str, str]:
    return {"X-Request-ID": str(uuid.uuid4())}


def _decode_tts_wav(payload: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            compression = wav.getcomptype()
            frames = wav.readframes(wav.getnframes())
    except (EOFError, wave.Error) as exc:
        raise RemoteSpeechError("Hermes Speech returned invalid WAV audio") from exc

    if (
        channels != 1
        or sample_width != 2
        or sample_rate != TTS_SAMPLE_RATE
        or compression != "NONE"
    ):
        raise RemoteSpeechError("Hermes Speech TTS must return mono 24 kHz signed 16-bit PCM WAV")
    return frames


class RemoteSpeechPorts:
    """One authenticated client implementing all three speech ports.

    STT and TTS use the asynchronous client. VAD remains synchronous because
    ``VadPort.probability`` is deliberately synchronous in the orchestrator.
    Both clients keep their LAN connections alive between frames and turns.
    """

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        token: str,
        timeout_seconds: float,
        voice: str | None = None,
        speed: float = 1.0,
        async_transport: httpx.AsyncBaseTransport | None = None,
        sync_transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Client-ID": client_id,
        }
        timeout = httpx.Timeout(timeout_seconds)
        self._async_client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=async_transport,
        )
        self._sync_client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=sync_transport,
        )
        self._warmup_lock = asyncio.Lock()
        self._voice = voice
        self._speed = speed
        self._ready = False
        self._closed = False

    @classmethod
    def from_env(cls) -> RemoteSpeechPorts:
        token = _required_env("HV_SPEECH_SERVICE_TOKEN")
        if len(token.encode("utf-8")) < 32:
            raise ValueError("HV_SPEECH_SERVICE_TOKEN must contain at least 32 bytes")
        raw_speed = os.environ.get("HV_KOKORO_SPEED", "1.0")
        try:
            speed = float(raw_speed)
        except ValueError as exc:
            raise ValueError("HV_KOKORO_SPEED must be a number") from exc
        if not math.isfinite(speed) or not 0.5 <= speed <= 2.0:
            raise ValueError("HV_KOKORO_SPEED must be between 0.5 and 2.0")
        return cls(
            base_url=_service_url(),
            client_id=_required_env("HV_SPEECH_CLIENT_ID"),
            token=token,
            timeout_seconds=_timeout_seconds(),
            voice=os.environ.get("HV_KOKORO_VOICE") or None,
            speed=speed,
        )

    async def warmup(self) -> None:
        """Verify that the shared service has finished loading its models."""
        async with self._warmup_lock:
            if self._ready:
                return
            response = await self._async_client.get("/readyz")
            _raise_for_status(response)
            body = _json_object(response, operation="readiness")
            if body.get("status") != "ready":
                raise RemoteSpeechError("Hermes Speech is not ready")
            self._ready = True

    def probability(self, frame: bytes) -> float:
        response = self._sync_client.post(
            "/v1/vad",
            content=frame,
            headers={
                **_request_headers(),
                "Content-Type": "audio/l16",
                "X-Audio-Sample-Rate": str(STT_SAMPLE_RATE),
            },
        )
        _raise_for_status(response)
        body = _json_object(response, operation="VAD")
        try:
            probability = float(body["speech_probability"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RemoteSpeechError("Hermes Speech returned an invalid VAD response") from exc
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise RemoteSpeechError("Hermes Speech returned an invalid VAD probability")
        return probability

    async def transcribe(self, pcm: bytes) -> str:
        response = await self._async_client.post(
            "/v1/stt",
            content=pcm,
            headers={
                **_request_headers(),
                "Content-Type": "audio/l16",
                "X-Audio-Sample-Rate": str(STT_SAMPLE_RATE),
            },
        )
        _raise_for_status(response)
        body = _json_object(response, operation="STT")
        text = body.get("text")
        if not isinstance(text, str):
            raise RemoteSpeechError("Hermes Speech returned an invalid transcription")
        return text.strip()

    async def verify_speaker(self, pcm: bytes) -> SpeakerDecision:
        response = await self._async_client.post(
            "/v1/speaker/verify",
            content=pcm,
            headers={
                **_request_headers(),
                "Content-Type": "audio/l16",
                "X-Audio-Sample-Rate": str(STT_SAMPLE_RATE),
            },
        )
        _raise_for_status(response)
        body = _json_object(response, operation="speaker verification")
        configured = body.get("configured")
        accepted = body.get("accepted")
        score = body.get("score")
        speaker = body.get("speaker")
        threshold = body.get("threshold")
        reason = body.get("reason")
        if not isinstance(configured, bool) or not isinstance(accepted, bool):
            raise RemoteSpeechError("Hermes Speech returned an invalid speaker decision")
        if score is not None:
            if isinstance(score, bool) or not isinstance(score, int | float):
                raise RemoteSpeechError("Hermes Speech returned an invalid speaker score")
            score = float(score)
            if not math.isfinite(score) or not -1.0 <= score <= 1.0:
                raise RemoteSpeechError("Hermes Speech returned an invalid speaker score")
        if speaker is not None and not isinstance(speaker, str):
            raise RemoteSpeechError("Hermes Speech returned an invalid speaker label")
        if isinstance(threshold, bool) or not isinstance(threshold, int | float):
            raise RemoteSpeechError("Hermes Speech returned an invalid speaker threshold")
        threshold = float(threshold)
        if not math.isfinite(threshold) or not 0.0 < threshold <= 1.0:
            raise RemoteSpeechError("Hermes Speech returned an invalid speaker threshold")
        if not isinstance(reason, str) or not reason:
            raise RemoteSpeechError("Hermes Speech returned an invalid speaker reason")
        return SpeakerDecision(
            configured=configured,
            accepted=accepted,
            score=score,
            speaker=speaker,
            threshold=threshold,
            reason=reason,
        )

    async def synthesize(self, text: str) -> bytes:
        payload: dict[str, object] = {"text": text, "speed": self._speed}
        if self._voice is not None:
            payload["voice"] = self._voice
        response = await self._async_client.post(
            "/v1/tts",
            json=payload,
            headers=_request_headers(),
        )
        _raise_for_status(response)
        return _decode_tts_wav(response.content)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._sync_client.close()
        await self._async_client.aclose()


def build_remote_speech_ports() -> tuple[
    RemoteSpeechPorts,
    RemoteSpeechPorts,
    RemoteSpeechPorts,
]:
    remote = RemoteSpeechPorts.from_env()
    return remote, remote, remote
