
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import scripts.verify_platform as verify


def test_apple_silicon_expects_mlx() -> None:
    with (
        patch("scripts.verify_platform.sys.platform", "darwin"),
        patch("scripts.verify_platform.platform.machine", return_value="arm64"),
    ):
        assert verify.expected_backend() == "mlx"


def test_other_platforms_expect_portable() -> None:
    with (
        patch("scripts.verify_platform.sys.platform", "win32"),
        patch("scripts.verify_platform.platform.machine", return_value="AMD64"),
    ):
        assert verify.expected_backend() == "portable"


def test_platform_guides_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in (
        "README-UBUNTU-LINUX.md",
        "README-MACOS-APPLE-SILICON.md",
        "README-MACOS-INTEL.md",
        "README-WINDOWS.md",
        "REAL-MACHINE-TESTING.md",
    ):
        assert (root / "docs" / "platform" / name).is_file()
