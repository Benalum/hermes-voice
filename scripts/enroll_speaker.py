#!/usr/bin/env python3
"""Enroll a speaker's voice into the speaker gate.

Records ~10s of audio from the default microphone (or reads a WAV file),
embeds it with resemblyzer, and appends the embedding to the gate's store.

Usage:
    # record from mic (needs sounddevice/pyaudio):
    python scripts/enroll_speaker.py --name alex --record 10
    # or from a WAV you already have (16 kHz mono int16 preferred):
    python scripts/enroll_speaker.py --name partner --wav path/to/clip.wav

The store path matches the [speaker_gate] config (default
~/.hermes-voice/speakers.json). Override with --store.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# Run from the repo root so the package import works.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_voice.kit.speaker_gate import SpeakerGate, SpeakerGateConfig


def _read_wav(path: Path, *, store: Path) -> bytes:
    """Load a WAV and return 16 kHz int16 mono PCM bytes."""
    try:
        import soundfile as sf
    except ImportError:
        raise SystemExit("soundfile is required to read WAV: uv pip install soundfile") from None
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data[:, 0]
    if sr != 16000:
        import resampy

        data = resampy.resample(data, sr, 16000)
    pcm = np.clip(data, -1.0, 1.0) * 32767.0
    return pcm.astype(np.int16).tobytes()


def _record(seconds: float, *, store: Path) -> bytes:
    try:
        import sounddevice as sd
    except ImportError:
        raise SystemExit("sounddevice is required to record: uv pip install sounddevice") from None
    print(f"Recording {seconds:g}s of audio for enrollment... speak now.")
    audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="int16")
    sd.wait()
    print("Recording complete.")
    return audio.tobytes()


def main() -> None:
    parser = argparse.ArgumentParser(description="Enroll a speaker into the gate")
    parser.add_argument("--name", required=True, help="speaker label, e.g. alex")
    parser.add_argument("--wav", type=Path, help="WAV file to enroll from")
    parser.add_argument("--record", type=float, help="record N seconds from mic")
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("~/.hermes-voice/speakers.json").expanduser(),
        help="gate store path (default ~/.hermes-voice/speakers.json)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="acceptance threshold (default 0.75)",
    )
    args = parser.parse_args()

    if not args.wav and not args.record:
        parser.error("provide --wav PATH or --record SECONDS")

    pcm = (
        _read_wav(args.wav, store=args.store)
        if args.wav
        else _record(args.record, store=args.store)
    )
    if len(pcm) < 8000:
        raise SystemExit("clip too short (< 0.5s); use a longer sample")

    cfg = SpeakerGateConfig(enabled=True, threshold=args.threshold, store=args.store)
    gate = SpeakerGate(cfg)
    emb = gate.embed(pcm)
    if emb is None:
        raise SystemExit("failed to embed audio (resemblyzer unavailable?)")
    gate.enroll(args.name, emb)
    print(f"Enrolled '{args.name}'. Current speakers: {gate.enrolled_names}")


if __name__ == "__main__":
    main()
