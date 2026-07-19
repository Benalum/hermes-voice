"""Select the correct Hermes Voice speech stack for the current host."""

from __future__ import annotations

import os
import platform
import sys

from hermes_voice.kit.ports import SttPort, TtsPort, VadPort

_VALID_BACKENDS = {"auto", "mlx", "portable", "remote"}


def detect_speech_backend() -> str:
    """Return 'mlx', 'portable', or the explicitly selected 'remote'."""

    requested = (
        os.environ.get(
            "HV_SPEECH_BACKEND",
            "auto",
        )
        .strip()
        .lower()
    )

    if requested not in _VALID_BACKENDS:
        allowed = ", ".join(sorted(_VALID_BACKENDS))

        raise ValueError(f"invalid HV_SPEECH_BACKEND {requested!r}; expected one of: {allowed}")

    machine = platform.machine().lower()

    apple_silicon = sys.platform == "darwin" and machine in {"arm64", "aarch64"}

    if requested == "mlx":
        if not apple_silicon:
            raise RuntimeError("the MLX speech backend requires Apple Silicon macOS")

        return "mlx"

    if requested == "portable":
        return "portable"

    if requested == "remote":
        return "remote"

    # Automatic selection:

    # Apple Silicon uses MLX; Ubuntu/Linux and other systems use portable.

    return "mlx" if apple_silicon else "portable"


def build_speech_ports() -> tuple[VadPort, SttPort, TtsPort]:
    """Construct the VAD, STT, and TTS adapters for this platform."""

    from hermes_voice.io.vad_silero import SileroVad

    backend = detect_speech_backend()

    if backend == "remote":
        from hermes_voice.io.remote_speech import build_remote_speech_ports

        return build_remote_speech_ports()

    if backend == "mlx":
        from hermes_voice.io.stt_parakeet import ParakeetStt
        from hermes_voice.io.tts_kokoro import KokoroTts

        return SileroVad(), ParakeetStt(), KokoroTts()

    from hermes_voice.io.stt_faster_whisper import FasterWhisperStt
    from hermes_voice.io.tts_kokoro_portable import PortableKokoroTts

    return SileroVad(), FasterWhisperStt(), PortableKokoroTts()
