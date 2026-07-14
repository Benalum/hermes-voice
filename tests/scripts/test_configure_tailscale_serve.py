from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

from hermes_voice.scripts import configure_tailscale_serve as serve

EXISTING_CONFIG = {
    "TCP": {
        "443": {"HTTPS": True},
        "8443": {"HTTPS": True},
    },
    "Web": {
        "hermes.example.ts.net:443": {
            "Handlers": {
                "/": {"Proxy": "http://127.0.0.1:8990"},
            }
        },
        "hermes.example.ts.net:8443": {
            "Handlers": {
                "/": {"Proxy": "http://127.0.0.1:9119"},
            }
        },
    },
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:8990", "http://127.0.0.1:8990"),
        ("http://localhost:8990/", "http://localhost:8990"),
    ],
)
def test_validate_backend_accepts_loopback(value: str, expected: str) -> None:
    assert serve._validate_backend(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:8990",
        "http://0.0.0.0:8990",
        "http://192.168.1.10:8990",
        "http://127.0.0.1",
        "http://127.0.0.1:8990/path",
    ],
)
def test_validate_backend_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        serve._validate_backend(value)


def test_validate_port() -> None:
    assert serve._validate_port("443") == 443
    with pytest.raises(argparse.ArgumentTypeError):
        serve._validate_port("0")


def test_macos_cli_fallback() -> None:
    candidate = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    with (
        patch("shutil.which", return_value=None),
        patch("platform.system", return_value="Darwin"),
        patch.object(Path, "is_file", new=lambda self: self == candidate),
    ):
        assert serve._find_tailscale_cli() == candidate


def test_serve_routes_parses_json() -> None:
    routes = serve._serve_routes(EXISTING_CONFIG)
    assert routes == (
        serve.ServeRoute(
            host="hermes.example.ts.net",
            port=443,
            path="/",
            proxy="http://127.0.0.1:8990",
        ),
        serve.ServeRoute(
            host="hermes.example.ts.net",
            port=8443,
            path="/",
            proxy="http://127.0.0.1:9119",
        ),
    )


def test_configure_reuses_existing_matching_route() -> None:
    with (
        patch.object(
            serve,
            "_find_tailscale_cli",
            return_value=Path("/usr/bin/tailscale"),
        ),
        patch.object(
            serve,
            "_read_serve_config",
            return_value=EXISTING_CONFIG,
        ),
        patch.object(serve, "_run_mutation") as mutation,
        patch.object(serve, "_platform_note", return_value="Linux detected."),
    ):
        serve.configure(
            backend="http://127.0.0.1:8990",
            https_port=None,
            force=False,
            dry_run=True,
        )

    mutation.assert_not_called()


def test_configure_refuses_to_replace_dashboard() -> None:
    with (
        patch.object(
            serve,
            "_find_tailscale_cli",
            return_value=Path("/usr/bin/tailscale"),
        ),
        patch.object(
            serve,
            "_read_serve_config",
            return_value=EXISTING_CONFIG,
        ),
        patch.object(serve, "_platform_note", return_value="Linux detected."),
        pytest.raises(RuntimeError, match="already serving"),
    ):
        serve.configure(
            backend="http://127.0.0.1:8990",
            https_port=8443,
            force=False,
            dry_run=True,
        )


def test_configure_free_port_builds_persistent_command() -> None:
    commands: list[list[str]] = []

    def record(command: list[str], *, dry_run: bool) -> None:
        assert dry_run is True
        commands.append(command)

    with (
        patch.object(
            serve,
            "_find_tailscale_cli",
            return_value=Path("/usr/bin/tailscale"),
        ),
        patch.object(
            serve,
            "_read_serve_config",
            return_value=EXISTING_CONFIG,
        ),
        patch.object(serve, "_run_mutation", side_effect=record),
        patch.object(serve, "_platform_note", return_value="Linux detected."),
    ):
        serve.configure(
            backend="http://127.0.0.1:8990",
            https_port=9443,
            force=False,
            dry_run=True,
        )

    assert commands == [
        [
            "/usr/bin/tailscale",
            "serve",
            "--bg",
            "--yes",
            "--https=9443",
            "http://127.0.0.1:8990",
        ]
    ]


def test_force_allows_explicit_replacement() -> None:
    commands: list[list[str]] = []

    def record(command: list[str], *, dry_run: bool) -> None:
        assert dry_run is True
        commands.append(command)

    with (
        patch.object(
            serve,
            "_find_tailscale_cli",
            return_value=Path("/usr/bin/tailscale"),
        ),
        patch.object(
            serve,
            "_read_serve_config",
            return_value=EXISTING_CONFIG,
        ),
        patch.object(serve, "_run_mutation", side_effect=record),
        patch.object(serve, "_platform_note", return_value="Linux detected."),
    ):
        serve.configure(
            backend="http://127.0.0.1:8990",
            https_port=8443,
            force=True,
            dry_run=True,
        )

    assert commands[0][4] == "--https=8443"
