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
