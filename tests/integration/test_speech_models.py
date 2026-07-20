"""Integration tests for the real MLX speech adapters. Run with: pytest -m models"""

import math
import struct

import pytest

pytestmark = pytest.mark.models

SAMPLE_RATE = 16000


def tone(frequency: float, seconds: float) -> bytes:
    samples = int(SAMPLE_RATE * seconds)
    return b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)))
        for i in range(samples)
    )


class TestSileroVad:
    def test_silence_scores_low(self) -> None:
        from hermes_voice.io.vad_silero import SileroVad

        vad = SileroVad()
        assert vad.probability(b"\x00\x00" * 512) < 0.3

    def test_frame_of_wrong_size_scores_zero(self) -> None:
        from hermes_voice.io.vad_silero import SileroVad

        assert SileroVad().probability(b"\x00\x00" * 100) == 0.0


class TestKokoroTts:
    async def test_synthesizes_non_silent_audio(self) -> None:
        from hermes_voice.io.tts_kokoro import KokoroTts

        tts = KokoroTts()
        pcm = await tts.synthesize("Hello from the voice gateway.")
        assert len(pcm) > 24000  # > 0.5s of 24 kHz int16 audio
        peak = max(abs(s[0]) for s in struct.iter_unpack("<h", pcm))
        assert peak > 1000


class TestParakeetStt:
    async def test_transcribes_synthesized_speech(self) -> None:
        """Round-trip: Kokoro speaks at 24 kHz, resampled to 16 kHz, parakeet reads it back."""
        import numpy as np

        from hermes_voice.io.stt_parakeet import ParakeetStt
        from hermes_voice.io.tts_kokoro import KokoroTts

        spoken = await KokoroTts().synthesize("hello world")
        audio24 = np.frombuffer(spoken, dtype=np.int16).astype(np.float32)
        indices = np.arange(0, len(audio24), 1.5)  # 24 kHz -> 16 kHz
        audio16 = audio24[indices.astype(np.int64)].astype(np.int16).tobytes()

        text = await ParakeetStt().transcribe(audio16)
        assert "hello" in text.lower()
