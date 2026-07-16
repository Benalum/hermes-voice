#!/usr/bin/env python3
"""Static checks that platform documentation matches the current repository."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "docs" / "platform"
FILES = (
    ROOT / "README.md",
    PLATFORM / "README.md",
    PLATFORM / "VALIDATION-STATUS.md",
    PLATFORM / "README-UBUNTU-LINUX.md",
    PLATFORM / "README-MACOS-APPLE-SILICON.md",
    PLATFORM / "README-MACOS-INTEL.md",
    PLATFORM / "README-WINDOWS.md",
    PLATFORM / "REAL-MACHINE-TESTING.md",
)

FORBIDDEN = (
    "feature/telegram-chat-topics",
    "rough setup guide",
    "tailscale serve reset",
)


def main() -> int:
    errors: list[str] = []
    for path in FILES:
        if not path.is_file():
            errors.append(f"missing documentation file: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            if forbidden in text:
                errors.append(f"{path.relative_to(ROOT)} contains stale text: {forbidden!r}")

        for link in re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", text):
            target = (path.parent / link).resolve()
            if not target.is_file():
                errors.append(f"{path.relative_to(ROOT)} links to missing file: {link}")

    required_snippets = {
        PLATFORM / "README-UBUNTU-LINUX.md": "uv sync --locked --extra speech --group dev",
        PLATFORM / "README-MACOS-APPLE-SILICON.md": "--expected-backend mlx",
        PLATFORM / "README-MACOS-INTEL.md": "--expected-backend portable",
        PLATFORM / "README-WINDOWS.md": "uv sync --locked --extra speech-portable --group dev",
    }
    for path, snippet in required_snippets.items():
        if path.is_file() and snippet not in path.read_text(encoding="utf-8"):
            errors.append(f"{path.relative_to(ROOT)} is missing {snippet!r}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"PASS: validated {len(FILES)} documentation files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
