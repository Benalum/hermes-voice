from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from hermes_voice.server.app import create_app


def _run_node_script(script: str, *, module_default: bool = False) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")

    repository = Path(__file__).resolve().parents[2]
    command = [node]
    if module_default:
        command.append("--experimental-default-type=module")
    command.append(str(repository / "tests/web" / script))
    result = subprocess.run(
        command,
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_connection_guard_rejects_stale_callbacks() -> None:
    _run_node_script("verify_connection_guard.mjs")


def test_main_ignores_stale_socket_and_microphone_callbacks() -> None:
    _run_node_script(
        "verify_main_connection_lifecycle.mjs",
        module_default=True,
    )


def test_connection_guard_module_is_served_as_javascript() -> None:
    with TestClient(create_app(mode="echo")) as client:
        response = client.get("/static/connection_guard.mjs")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "export class ConnectionGuard" in response.text
