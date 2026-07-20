from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_tailscale_serve_configs_are_private_and_target_separate_gateways() -> None:
    for agent in ("hermes1", "hermes2"):
        path = ROOT / "deploy" / "tailscale" / f"{agent}-serve.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        domain = "${TS_CERT_DOMAIN}:443"
        assert config["AllowFunnel"][domain] is False
        assert config["Web"][domain]["Handlers"]["/"]["Proxy"] == (f"http://{agent}-voice:8990")


def test_compose_keeps_public_ports_on_loopback() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert '"127.0.0.1:${HERMES1_VOICE_PORT:-8991}:8990"' in compose
    assert '"127.0.0.1:${HERMES2_VOICE_PORT:-8992}:8990"' in compose
    assert "AllowFunnel" not in compose
    assert "deploy/compose/state/hermes1-agent:/opt/data" in compose
    assert "deploy/compose/state/hermes2-agent:/opt/data" in compose


@pytest.mark.skipif(os.name == "nt", reason="the configurator runs inside a Linux host")
def test_agent_configurator_is_valid_bash() -> None:
    script = ROOT / "deploy" / "compose" / "configure-agent.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
