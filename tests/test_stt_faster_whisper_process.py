from __future__ import annotations

import asyncio
import io
import json

import pytest

from hermes_voice.io import stt_faster_whisper as module


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("darwin", "x86_64", True),
        ("darwin", "arm64", False),
        ("linux", "x86_64", False),
        ("win32", "AMD64", False),
    ],
)
def test_process_isolation_selection(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(module.sys, "platform", system)
    monkeypatch.setattr(module.platform, "machine", lambda: machine)

    assert module._needs_process_isolation() is expected


def test_worker_command_starts_clean_interpreter() -> None:
    worker = module._IsolatedFasterWhisperWorker(
        "tiny.en",
        "cpu",
        "int8",
    )

    assert worker._command() == [
        module.sys.executable,
        "-I",
        "-m",
        "hermes_voice.io.stt_faster_whisper_worker",
        "--model-id",
        "tiny.en",
        "--device",
        "cpu",
        "--compute-type",
        "int8",
    ]


def test_worker_protocol_round_trip() -> None:
    stream = io.BytesIO()
    response = {
        "status": "ok",
        "text": "hello",
    }

    module._write_frame(
        stream,
        json.dumps(response).encode("utf-8"),
    )
    stream.seek(0)

    assert (
        module._decode_worker_response(
            module._read_frame(stream),
        )
        == response
    )


def test_intel_adapter_uses_dedicated_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class FakeWorker:
        def __init__(
            self,
            model_id: str,
            device: str,
            compute_type: str,
        ) -> None:
            events.append((model_id, device, compute_type))

        def warmup(self) -> None:
            events.append("warmup")

        def transcribe(self, pcm: bytes) -> str:
            events.append(pcm)
            return "worker transcript"

        def close(self) -> None:
            events.append("close")

    monkeypatch.setattr(
        module,
        "_needs_process_isolation",
        lambda: True,
    )
    monkeypatch.setattr(
        module,
        "_IsolatedFasterWhisperWorker",
        FakeWorker,
    )

    stt = module.FasterWhisperStt(model_id="tiny.en")
    try:
        asyncio.run(stt.warmup())
        transcript = asyncio.run(
            stt.transcribe(b"\x00\x00"),
        )
    finally:
        stt.close()

    assert transcript == "worker transcript"
    assert events == [
        ("tiny.en", "cpu", "int8"),
        "warmup",
        b"\x00\x00",
        "close",
    ]
