from __future__ import annotations

from unittest.mock import patch

import pytest

from hermes_voice.io.speech_factory import detect_speech_backend


def test_linux_auto_selects_portable() -> None:
    with (
        patch("hermes_voice.io.speech_factory.sys.platform", "linux"),
        patch(
            "hermes_voice.io.speech_factory.platform.machine",
            return_value="x86_64",
        ),
        patch.dict("os.environ", {}, clear=True),
    ):
        assert detect_speech_backend() == "portable"


def test_apple_silicon_auto_selects_mlx() -> None:
    with (
        patch("hermes_voice.io.speech_factory.sys.platform", "darwin"),
        patch(
            "hermes_voice.io.speech_factory.platform.machine",
            return_value="arm64",
        ),
        patch.dict("os.environ", {}, clear=True),
    ):
        assert detect_speech_backend() == "mlx"


def test_portable_override_is_allowed_on_linux() -> None:
    with (
        patch("hermes_voice.io.speech_factory.sys.platform", "linux"),
        patch(
            "hermes_voice.io.speech_factory.platform.machine",
            return_value="x86_64",
        ),
        patch.dict(
            "os.environ",
            {"HV_SPEECH_BACKEND": "portable"},
            clear=True,
        ),
    ):
        assert detect_speech_backend() == "portable"


def test_mlx_override_is_rejected_on_linux() -> None:
    with (
        patch("hermes_voice.io.speech_factory.sys.platform", "linux"),
        patch(
            "hermes_voice.io.speech_factory.platform.machine",
            return_value="x86_64",
        ),
        patch.dict(
            "os.environ",
            {"HV_SPEECH_BACKEND": "mlx"},
            clear=True,
        ),
        pytest.raises(
            RuntimeError,
            match="requires Apple Silicon",
        ),
    ):
        detect_speech_backend()


def test_invalid_backend_is_rejected() -> None:
    with (
        patch.dict(
            "os.environ",
            {"HV_SPEECH_BACKEND": "invalid"},
            clear=True,
        ),
        pytest.raises(
            ValueError,
            match="invalid HV_SPEECH_BACKEND",
        ),
    ):
        detect_speech_backend()
