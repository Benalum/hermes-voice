#!/usr/bin/env python3
"""Hermes Agent command-provider bridge for the shared speech service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


class BridgeError(RuntimeError):
    pass


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BridgeError(f"cannot read speech configuration: {path}") from exc
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _settings(path: Path) -> tuple[str, str, str, float]:
    values = _read_env(path) if path.is_file() else {}
    for name in (
        "HV_SPEECH_SERVICE_URL",
        "HV_SPEECH_CLIENT_ID",
        "HV_SPEECH_SERVICE_TOKEN",
        "HV_SPEECH_REQUEST_TIMEOUT_SECONDS",
    ):
        if name in os.environ:
            values[name] = os.environ[name]
    url = values.get("HV_SPEECH_SERVICE_URL", "").rstrip("/")
    client_id = values.get("HV_SPEECH_CLIENT_ID", "")
    token = values.get("HV_SPEECH_SERVICE_TOKEN", "")
    try:
        timeout = float(values.get("HV_SPEECH_REQUEST_TIMEOUT_SECONDS", "180"))
    except ValueError as exc:
        raise BridgeError("invalid speech request timeout") from exc
    if not url.startswith(("http://", "https://")):
        raise BridgeError("speech service URL must use http or https")
    if not client_id or not token:
        raise BridgeError("speech client ID or token is missing")
    if timeout <= 0 or timeout > 900:
        raise BridgeError("speech request timeout must be between 0 and 900 seconds")
    return url, client_id, token, timeout


def _request(
    url: str,
    client_id: str,
    token: str,
    timeout: float,
    body: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Client-ID": client_id,
            "Content-Type": content_type,
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            return response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise BridgeError(f"speech service returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BridgeError(f"cannot reach speech service: {exc.reason}") from exc


def _convert_to_wav(input_path: Path, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise BridgeError("ffmpeg is required for Telegram voice transcription")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
            check=True,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BridgeError("ffmpeg could not convert the incoming audio") from exc


def transcribe(config: Path, input_path: Path, output_path: Path) -> None:
    if not input_path.is_file():
        raise BridgeError(f"audio input does not exist: {input_path}")
    base_url, client_id, token, timeout = _settings(config)
    with tempfile.TemporaryDirectory(prefix="hermes-speech-stt-") as temp_dir:
        wav_path = Path(temp_dir) / "input.wav"
        _convert_to_wav(input_path, wav_path)
        audio = wav_path.read_bytes()
    response, _media_type = _request(
        f"{base_url}/v1/stt",
        client_id,
        token,
        timeout,
        audio,
        "audio/wav",
    )
    try:
        text = str(json.loads(response)["text"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise BridgeError("speech service returned an invalid transcription") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def synthesize(
    config: Path,
    input_path: Path,
    output_path: Path,
    voice: str | None,
    speed: float,
) -> None:
    if not input_path.is_file():
        raise BridgeError(f"text input does not exist: {input_path}")
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        raise BridgeError("TTS input text is empty")
    base_url, client_id, token, timeout = _settings(config)
    payload: dict[str, object] = {"text": text, "speed": speed}
    if voice:
        payload["voice"] = voice
    response, media_type = _request(
        f"{base_url}/v1/tts",
        client_id,
        token,
        timeout,
        json.dumps(payload).encode("utf-8"),
        "application/json",
    )
    if media_type not in {"audio/wav", "audio/x-wav"} or not response.startswith(b"RIFF"):
        raise BridgeError("speech service returned invalid WAV audio")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.getenv("HERMES_SPEECH_CONFIG", "/etc/hermes/voice.env")),
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    stt = subparsers.add_parser("stt")
    stt.add_argument("--input", type=Path, required=True)
    stt.add_argument("--output", type=Path, required=True)

    tts = subparsers.add_parser("tts")
    tts.add_argument("--input", type=Path, required=True)
    tts.add_argument("--output", type=Path, required=True)
    tts.add_argument("--voice", default=None)
    tts.add_argument("--speed", type=float, default=1.0)

    args = parser.parse_args()
    try:
        if args.operation == "stt":
            transcribe(args.config, args.input, args.output)
        else:
            synthesize(args.config, args.input, args.output, args.voice, args.speed)
    except BridgeError as exc:
        parser.exit(1, f"hermes-speech-bridge: {exc}\n")


if __name__ == "__main__":
    main()
