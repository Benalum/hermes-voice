from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from hermes_voice.io.stt_faster_whisper import FasterWhisperStt
from hermes_voice.io.tts_kokoro_portable import PortableKokoroTts


@pytest.mark.asyncio
async def test_stt_blank_audio_returns_blank_without_loading_model() -> None:
    stt = FasterWhisperStt()
    stt._load = MagicMock()  # type: ignore[method-assign]

    assert await stt.transcribe(b"") == ""
    stt._load.assert_not_called()


@pytest.mark.asyncio
async def test_stt_discards_incomplete_final_pcm_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hermes_voice.io.stt_faster_whisper._needs_process_isolation",
        lambda: False,
    )

    stt = FasterWhisperStt()
    stt._transcribe_sync = MagicMock(return_value="hello")  # type: ignore[method-assign]

    try:
        result = await stt.transcribe(b"\x00\x00\x01")

        assert result == "hello"
        stt._transcribe_sync.assert_called_once_with(b"\x00\x00")
    finally:
        stt.close()


@pytest.mark.asyncio
async def test_tts_blank_text_returns_blank_without_loading_pipeline() -> None:
    tts = PortableKokoroTts()
    tts._load = MagicMock()  # type: ignore[method-assign]

    assert await tts.synthesize("   ") == b""
    tts._load.assert_not_called()


@pytest.mark.parametrize("speed", [0.0, 0.49, 2.01])
def test_tts_rejects_invalid_speed(speed: float) -> None:
    with pytest.raises(
        ValueError,
        match=r"must be between 0\.5 and 2\.0",
    ):
        PortableKokoroTts(speed=speed)


def test_tts_speed_change_applies_to_future_synthesis() -> None:
    tts = PortableKokoroTts(speed=1.0)
    seen_speeds: list[float] = []

    def fake_pipeline(
        _text: str,
        *,
        voice: str,
        speed: float,
    ):
        del voice
        seen_speeds.append(speed)
        yield "", "", np.array([0.0], dtype=np.float32)

    tts._pipeline = fake_pipeline
    tts.set_speed(1.25)

    assert tts._synthesize_sync("hello")
    assert seen_speeds == [1.25]


def test_tts_clips_audio_before_int16_conversion() -> None:
    tts = PortableKokoroTts()

    def fake_pipeline(
        _text: str,
        *,
        voice: str,
        speed: float,
    ):
        del voice, speed
        yield (
            "",
            "",
            np.array(
                [-2.0, -1.0, 0.0, 1.0, 2.0],
                dtype=np.float32,
            ),
        )

    tts._pipeline = fake_pipeline

    pcm = tts._synthesize_sync("hello")
    samples = np.frombuffer(pcm, dtype=np.int16)

    assert samples.tolist() == [
        -32767,
        -32767,
        0,
        32767,
        32767,
    ]
