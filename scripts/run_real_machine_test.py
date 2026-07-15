#!/usr/bin/env python3
"""Run a real-model parrot loop and save platform evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def wait_for_health(
    url: str,
    timeout: float,
    *,
    process: subprocess.Popen[Any] | None = None,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"gateway exited during startup with code {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("models") == "warm":
                return payload
        except Exception as exc:  # pragma: no cover - real machine path
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"gateway did not become healthy: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8991)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports" / "real-machine")
    args = parser.parse_args()

    args.report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_name = f"{platform.system().lower()}-{platform.machine()}-{timestamp}.json"
    report_path = args.report_dir / report_name
    report: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "os": platform.system(),
        "release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "port": args.port,
        "steps": {},
    }

    with tempfile.TemporaryDirectory(
        prefix="hermes-voice-real-",
        ignore_cleanup_errors=sys.platform == "win32",
    ) as temp:
        pcm_path = Path(temp) / "probe.pcm"
        generation = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_probe_audio.py"), str(pcm_path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        report["steps"]["generate_probe"] = {
            "returncode": generation.returncode,
            "stdout": generation.stdout,
            "stderr": generation.stderr,
        }
        if generation.returncode != 0:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(generation.stdout)
            print(generation.stderr, file=sys.stderr)
            print(f"FAIL report: {report_path}")
            return 1

        env = os.environ.copy()
        env.update({"HV_MODE": "parrot", "HV_SPEECH_BACKEND": "auto"})
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "hermes_voice.server.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
        ]
        log_path = Path(temp) / "uvicorn.log"
        failure: Exception | None = None
        success = False
        with log_path.open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                health = wait_for_health(
                    f"http://127.0.0.1:{args.port}/healthz",
                    args.timeout,
                )
                report["health"] = health
                e2e = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "tests" / "e2e" / "verify.py"),
                        f"ws://127.0.0.1:{args.port}/ws",
                        "",
                        "--pcm-file",
                        str(pcm_path),
                        "--timeout",
                        str(args.timeout),
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                report["steps"]["websocket_loop"] = {
                    "returncode": e2e.returncode,
                    "stdout": e2e.stdout,
                    "stderr": e2e.stderr,
                }
                for route in ("/", "/static/main.js"):
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{args.port}{route}", timeout=10
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"{route} returned {response.status}")
                success = e2e.returncode == 0
            except Exception as exc:
                failure = exc
            finally:
                if server.poll() is None:
                    server.terminate()
                try:
                    server.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)
                report["server_log"] = log_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )[-20000:]

    report["result"] = "pass" if success else "fail"
    report["manual_checks_required"] = [
        "physical browser microphone",
        "audible browser speaker output",
        "Telegram topic round trip",
        "Stop Speech and barge-in",
        "Tailscale HTTPS from another device",
        "startup after reboot or login",
    ]
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    websocket_loop = report["steps"].get("websocket_loop")
    if isinstance(websocket_loop, dict):
        print(websocket_loop.get("stdout", ""))
    if failure is not None:
        print(f"ERROR: {report['error']}", file=sys.stderr)
        server_log = str(report.get("server_log", ""))
        if server_log:
            print(server_log, file=sys.stderr)
    print(f"{report['result'].upper()} report: {report_path}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
