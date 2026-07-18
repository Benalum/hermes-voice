#!/usr/bin/env python3
"""Model-free platform verification for clean installs and CI."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expected_backend() -> str:
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return "mlx"
    return "portable"


def adapter_modules(backend: str) -> tuple[str, ...]:
    common = ("hermes_voice.io.vad_silero",)
    if backend == "mlx":
        return (*common, "hermes_voice.io.stt_parakeet", "hermes_voice.io.tts_kokoro")
    return (*common, "hermes_voice.io.stt_faster_whisper", "hermes_voice.io.tts_kokoro_portable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-backend", choices=("mlx", "portable"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from hermes_voice.io.speech_factory import detect_speech_backend

    detected = detect_speech_backend()
    expected = args.expected_backend or expected_backend()
    errors: list[str] = []

    if detected != expected:
        errors.append(f"expected backend {expected!r}, detected {detected!r}")

    imported: list[str] = []
    for name in adapter_modules(detected):
        try:
            importlib.import_module(name)
            imported.append(name)
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors.append(f"failed to import {name}: {type(exc).__name__}: {exc}")

    required_paths = (
        ROOT / "README.md",
        ROOT / "config.example.toml",
        ROOT / "hermes_voice" / "web" / "index.html",
        ROOT / "hermes_voice" / "web" / "main.js",
        ROOT / "docs" / "platform" / "README.md",
    )
    for path in required_paths:
        if not path.is_file():
            errors.append(f"missing required path: {path.relative_to(ROOT)}")

    tools = {name: shutil.which(name) for name in ("ffmpeg", "git", "node", "tailscale", "uv")}
    if sys.platform == "darwin" and tools["ffmpeg"] is None:
        errors.append("ffmpeg is required on macOS for speech decoding")
    report = {
        "os": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "backend": detected,
        "imports": imported,
        "tools": tools,
        "errors": errors,
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"OS: {report['os']} {report['release']} ({report['architecture']})")
        print(f"Python: {report['python']}")
        print(f"Speech backend: {detected}")
        for name in imported:
            print(f"PASS import {name}")
        for name, value in tools.items():
            print(f"tool {name}: {value or 'not found'}")
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
