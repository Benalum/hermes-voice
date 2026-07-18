from __future__ import annotations

import asyncio
import io
import json
import os

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
            **_timeouts: float,
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


def test_worker_does_not_preload_numpy_before_faster_whisper() -> None:
    from hermes_voice.io import stt_faster_whisper_worker as worker_module

    assert "np" not in vars(worker_module)


def test_worker_accepts_pinned_intel_ctranslate2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_voice.io import stt_faster_whisper_worker as worker_module

    monkeypatch.setattr(worker_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        worker_module.platform,
        "machine",
        lambda: "x86_64",
    )
    monkeypatch.setattr(
        worker_module.metadata,
        "version",
        lambda _name: "4.3.1",
    )

    worker_module._validate_ctranslate2_runtime()


def test_worker_rejects_unpinned_intel_ctranslate2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_voice.io import stt_faster_whisper_worker as worker_module

    monkeypatch.setattr(worker_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        worker_module.platform,
        "machine",
        lambda: "x86_64",
    )
    monkeypatch.setattr(
        worker_module.metadata,
        "version",
        lambda _name: "4.8.1",
    )

    with pytest.raises(
        RuntimeError,
        match=r"requires ctranslate2 4\.3\.1; found 4\.8\.1",
    ):
        worker_module._validate_ctranslate2_runtime()


def test_worker_allows_current_ctranslate2_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_voice.io import stt_faster_whisper_worker as worker_module

    monkeypatch.setattr(worker_module.sys, "platform", "linux")
    monkeypatch.setattr(
        worker_module.platform,
        "machine",
        lambda: "x86_64",
    )

    def unexpected_version_lookup(_name: str) -> str:
        raise AssertionError("version lookup should not run outside Intel macOS")

    monkeypatch.setattr(
        worker_module.metadata,
        "version",
        unexpected_version_lookup,
    )

    worker_module._validate_ctranslate2_runtime()


def test_worker_uses_one_cpu_thread_on_intel_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_voice.io import stt_faster_whisper_worker as worker_module

    monkeypatch.setattr(worker_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        worker_module.platform,
        "machine",
        lambda: "x86_64",
    )

    assert worker_module._is_intel_mac()
    assert worker_module._ctranslate2_cpu_threads() == 1


def test_worker_preserves_default_cpu_threads_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hermes_voice.io import stt_faster_whisper_worker as worker_module

    monkeypatch.setattr(worker_module.sys, "platform", "linux")
    monkeypatch.setattr(
        worker_module.platform,
        "machine",
        lambda: "x86_64",
    )

    assert not worker_module._is_intel_mac()
    assert worker_module._ctranslate2_cpu_threads() == 0


def test_worker_response_read_times_out_when_process_is_silent() -> None:
    read_fd, write_fd = os.pipe()
    try:
        with (
            os.fdopen(read_fd, "rb", buffering=0) as stream,
            pytest.raises(
                TimeoutError,
                match="timed out waiting",
            ),
        ):
            module._read_frame_with_timeout(
                stream,
                0.01,
            )
    finally:
        os.close(write_fd)


def test_worker_response_read_times_out_on_partial_frame() -> None:
    read_fd, write_fd = os.pipe()
    with (
        os.fdopen(read_fd, "rb", buffering=0) as reader,
        os.fdopen(write_fd, "wb", buffering=0) as writer,
    ):
        writer.write(module._FRAME_HEADER.pack(8))
        writer.write(b"x")
        writer.flush()

        with pytest.raises(
            TimeoutError,
            match="timed out waiting",
        ):
            module._read_frame_with_timeout(
                reader,
                0.01,
            )


def test_threaded_worker_response_read_times_out_for_non_socket_pipe() -> None:
    read_fd, write_fd = os.pipe()
    try:
        with (
            os.fdopen(read_fd, "rb", buffering=0) as stream,
            pytest.raises(
                TimeoutError,
                match="timed out waiting",
            ),
        ):
            module._read_frame_with_thread_timeout(stream, 0.01)
    finally:
        os.close(write_fd)


def test_transcription_timeout_closes_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = module._IsolatedFasterWhisperWorker(
        "tiny.en",
        "cpu",
        "int8",
        transcribe_timeout_s=0.01,
    )
    process = type(
        "FakeProcess",
        (),
        {"stdin": io.BytesIO()},
    )()
    events: list[str] = []

    monkeypatch.setattr(
        worker,
        "_start",
        lambda: process,
    )

    def timeout_receive(
        _process: object,
        *,
        timeout_s: float,
        operation: str,
    ) -> dict[str, object]:
        assert timeout_s == 0.01
        assert operation == "transcription"
        raise TimeoutError("worker timed out")

    monkeypatch.setattr(
        worker,
        "_receive",
        timeout_receive,
    )
    monkeypatch.setattr(
        worker,
        "close",
        lambda: events.append("close"),
    )

    with pytest.raises(TimeoutError, match="worker timed out"):
        worker.transcribe(b"\x00\x00")

    assert events == ["close"]


def test_stt_close_stops_worker_before_waiting_for_executor() -> None:
    events: list[object] = []

    class FakeWorker:
        def close(self) -> None:
            events.append("worker.close")

    class FakeExecutor:
        def shutdown(
            self,
            *,
            wait: bool,
            cancel_futures: bool,
        ) -> None:
            events.append(("executor.shutdown", wait, cancel_futures))

    stt = object.__new__(module.FasterWhisperStt)
    stt._closed = False
    stt._worker = FakeWorker()
    stt._executor = FakeExecutor()

    stt.close()
    stt.close()

    assert events == [
        "worker.close",
        ("executor.shutdown", True, True),
    ]


def test_stt_close_does_not_wait_if_worker_shutdown_fails() -> None:
    events: list[object] = []

    class FailingWorker:
        def close(self) -> None:
            events.append("worker.close")
            raise RuntimeError("worker stuck")

    class FakeExecutor:
        def shutdown(
            self,
            *,
            wait: bool,
            cancel_futures: bool,
        ) -> None:
            events.append(("executor.shutdown", wait, cancel_futures))

    stt = object.__new__(module.FasterWhisperStt)
    stt._closed = False
    stt._worker = FailingWorker()
    stt._executor = FakeExecutor()

    with pytest.raises(RuntimeError, match="worker stuck"):
        stt.close()

    assert events == [
        "worker.close",
        ("executor.shutdown", False, True),
    ]


@pytest.mark.parametrize(
    "value",
    [0, -1, float("nan"), float("inf")],
)
def test_worker_rejects_invalid_timeouts(value: float) -> None:
    with pytest.raises(
        ValueError,
        match="finite positive number",
    ):
        module._IsolatedFasterWhisperWorker(
            "tiny.en",
            "cpu",
            "int8",
            start_timeout_s=value,
        )


def test_nonisolated_adapter_ignores_worker_timeout_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "_needs_process_isolation",
        lambda: False,
    )
    monkeypatch.setenv(
        "HV_WHISPER_WORKER_START_TIMEOUT_S",
        "invalid",
    )

    stt = module.FasterWhisperStt(model_id="tiny.en")
    stt.close()


def test_isolated_adapter_passes_configured_worker_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, float] = {}

    class FakeWorker:
        def __init__(
            self,
            _model_id: str,
            _device: str,
            _compute_type: str,
            *,
            start_timeout_s: float,
            transcribe_timeout_s: float,
            shutdown_timeout_s: float,
        ) -> None:
            captured.update(
                start=start_timeout_s,
                transcribe=transcribe_timeout_s,
                shutdown=shutdown_timeout_s,
            )

        def close(self) -> None:
            return None

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

    stt = module.FasterWhisperStt(
        model_id="tiny.en",
        worker_start_timeout_s=11,
        worker_transcribe_timeout_s=12,
        worker_shutdown_timeout_s=13,
    )
    stt.close()

    assert captured == {
        "start": 11.0,
        "transcribe": 12.0,
        "shutdown": 13.0,
    }


class PartialWriteBuffer(io.BytesIO):
    """Binary stream that accepts only a few bytes per write."""

    def __init__(self, max_write: int = 3) -> None:
        super().__init__()
        self.max_write = max_write
        self.write_calls = 0

    def write(self, data: bytes) -> int:
        self.write_calls += 1
        return super().write(data[: self.max_write])


class StalledWriteBuffer(io.BytesIO):
    """Binary stream that never makes write progress."""

    def write(self, _data: bytes) -> int:
        return 0


@pytest.mark.parametrize(
    "module_name",
    [
        "parent",
        "worker",
    ],
)
def test_frame_writer_completes_partial_writes(
    module_name: str,
) -> None:
    if module_name == "parent":
        write_frame = module._write_frame
        read_frame = module._read_frame
    else:
        from hermes_voice.io import (
            stt_faster_whisper_worker as worker_module,
        )

        write_frame = worker_module._write_frame
        read_frame = worker_module._read_frame

    payload = b"partial-write-frame-test"
    stream = PartialWriteBuffer(max_write=3)

    write_frame(stream, payload)

    assert stream.write_calls > 1

    stream.seek(0)
    assert read_frame(stream) == payload


@pytest.mark.parametrize(
    "module_name",
    [
        "parent",
        "worker",
    ],
)
def test_frame_writer_rejects_no_progress(
    module_name: str,
) -> None:
    if module_name == "parent":
        write_frame = module._write_frame
    else:
        from hermes_voice.io import (
            stt_faster_whisper_worker as worker_module,
        )

        write_frame = worker_module._write_frame

    with pytest.raises(
        OSError,
        match="made no progress",
    ):
        write_frame(
            StalledWriteBuffer(),
            b"payload",
        )
