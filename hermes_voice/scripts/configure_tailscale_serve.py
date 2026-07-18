"""Safely configure persistent Tailscale Serve for Hermes Voice."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_BACKEND = "http://127.0.0.1:8990"
DEFAULT_NEW_HTTPS_PORT = 443

_MACOS_CLI_CANDIDATES = (
    Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
    Path("/Applications/Tailscale.app/Contents/Macos/tailscale"),
)


@dataclass(frozen=True)
class ServeRoute:
    host: str
    port: int
    path: str
    proxy: str

    @property
    def url(self) -> str:
        port_suffix = "" if self.port == 443 else f":{self.port}"
        path_suffix = "" if self.path == "/" else self.path
        return f"https://{self.host}{port_suffix}{path_suffix}"


def _find_tailscale_cli() -> Path:
    """Return the local Tailscale CLI path or raise a useful error."""
    discovered = shutil.which("tailscale") or shutil.which("tailscale.exe")
    if discovered:
        return Path(discovered)

    if platform.system() == "Darwin":
        for candidate in _MACOS_CLI_CANDIDATES:
            if candidate.is_file():
                return candidate

    if platform.system() == "Windows":
        program_files = os.environ.get("PROGRAMFILES")
        if program_files:
            candidate = Path(program_files) / "Tailscale" / "tailscale.exe"
            if candidate.is_file():
                return candidate

    raise RuntimeError(
        "Tailscale CLI was not found. Install Tailscale, connect this device "
        "to a tailnet, and ensure the tailscale command is available."
    )


def _validate_backend(value: str) -> str:
    """Require a loopback HTTP backend so Serve remains the network edge."""
    parsed = urlparse(value)
    if parsed.scheme != "http":
        raise argparse.ArgumentTypeError("backend must use http://")

    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise argparse.ArgumentTypeError("backend must listen on 127.0.0.1 or localhost")

    if parsed.port is None:
        raise argparse.ArgumentTypeError("backend must include a port")

    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("backend must not include a path, query, or fragment")

    return value.rstrip("/")


def _validate_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("HTTPS port must be an integer") from exc

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("HTTPS port must be between 1 and 65535")

    return port


def _normalize_proxy(value: str) -> str:
    return value.rstrip("/")


def _read_serve_config(cli: Path) -> dict[str, object]:
    result = subprocess.run(
        [str(cli), "serve", "status", "--json"],
        check=True,
        text=True,
        capture_output=True,
    )

    if not result.stdout.strip():
        return {}

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Tailscale returned invalid Serve JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Tailscale Serve JSON must be an object")

    return payload


def _serve_routes(config: dict[str, object]) -> tuple[ServeRoute, ...]:
    raw_web = config.get("Web", {})
    if not isinstance(raw_web, dict):
        return ()

    routes: list[ServeRoute] = []
    for raw_host_port, raw_server in raw_web.items():
        if not isinstance(raw_host_port, str) or not isinstance(raw_server, dict):
            continue

        try:
            host, raw_port = raw_host_port.rsplit(":", 1)
            port = int(raw_port)
        except (ValueError, TypeError):
            continue

        handlers = raw_server.get("Handlers", {})
        if not isinstance(handlers, dict):
            continue

        for raw_path, raw_handler in handlers.items():
            if not isinstance(raw_path, str) or not isinstance(raw_handler, dict):
                continue
            proxy = raw_handler.get("Proxy")
            if not isinstance(proxy, str):
                continue
            routes.append(
                ServeRoute(
                    host=host,
                    port=port,
                    path=raw_path,
                    proxy=_normalize_proxy(proxy),
                )
            )

    return tuple(routes)


def _matching_routes(
    routes: tuple[ServeRoute, ...],
    *,
    backend: str,
) -> tuple[ServeRoute, ...]:
    normalized = _normalize_proxy(backend)
    return tuple(route for route in routes if route.path == "/" and route.proxy == normalized)


def _route_on_port(
    routes: tuple[ServeRoute, ...],
    *,
    port: int,
) -> ServeRoute | None:
    return next(
        (route for route in routes if route.port == port and route.path == "/"),
        None,
    )


def _run_mutation(command: list[str], *, dry_run: bool) -> None:
    print("+ " + " ".join(command))
    if dry_run:
        return
    subprocess.run(command, check=True)


def _platform_note() -> str:
    system = platform.system()
    if system == "Linux":
        return (
            "Linux detected. Ensure tailscaled is enabled under systemd. "
            "Background Serve configuration persists across reboots."
        )
    if system == "Darwin":
        return (
            "macOS detected. GUI Tailscale resumes after user login; the "
            "CLI-only tailscaled variant can run before login."
        )
    if system == "Windows":
        return (
            "Windows detected. Tailscale can run unattended, but native Windows "
            "Hermes Voice speech installation is not currently documented."
        )
    return f"{system or 'Unknown OS'} detected."


def configure(
    *,
    backend: str,
    https_port: int | None,
    force: bool,
    dry_run: bool,
) -> None:
    cli = _find_tailscale_cli()
    print(_platform_note())

    config = _read_serve_config(cli)
    routes = _serve_routes(config)
    matching = _matching_routes(routes, backend=backend)

    if https_port is None and matching:
        print("Hermes Voice is already hosted by Tailscale Serve:")
        for route in matching:
            print(f"  {route.url} -> {route.proxy}")
        print("No changes required.")
        return

    selected_port = https_port or DEFAULT_NEW_HTTPS_PORT
    occupied = _route_on_port(routes, port=selected_port)

    if occupied is not None and occupied.proxy == _normalize_proxy(backend):
        print(f"Hermes Voice is already hosted at {occupied.url} -> {occupied.proxy}")
        print("No changes required.")
        return

    if occupied is not None and not force:
        raise RuntimeError(
            f"HTTPS port {selected_port} is already serving "
            f"{occupied.proxy}. Choose another port with --https-port, "
            "or use --force only when replacement is intentional."
        )

    _run_mutation(
        [
            str(cli),
            "serve",
            "--bg",
            "--yes",
            f"--https={selected_port}",
            backend,
        ],
        dry_run=dry_run,
    )

    if dry_run:
        print("Dry run complete; no Serve configuration was changed.")
    else:
        print("Tailscale Serve configured successfully.")
        subprocess.run([str(cli), "serve", "status"], check=True)


def disable(*, https_port: int, dry_run: bool) -> None:
    cli = _find_tailscale_cli()
    _run_mutation(
        [str(cli), "serve", f"--https={https_port}", "off"],
        dry_run=dry_run,
    )
    if not dry_run:
        subprocess.run([str(cli), "serve", "status"], check=True)


def show_status() -> None:
    cli = _find_tailscale_cli()
    subprocess.run([str(cli), "serve", "status"], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Expose Hermes Voice privately over HTTPS with persistent, "
            "conflict-safe Tailscale Serve configuration."
        )
    )
    parser.add_argument(
        "--backend",
        type=_validate_backend,
        default=DEFAULT_BACKEND,
        help=f"local Hermes Voice URL (default: {DEFAULT_BACKEND})",
    )
    parser.add_argument(
        "--https-port",
        type=_validate_port,
        default=None,
        help=(
            "tailnet HTTPS port; by default, reuse an existing matching route "
            f"or create port {DEFAULT_NEW_HTTPS_PORT} when it is free"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a different root Serve route on the selected port",
    )

    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--disable",
        action="store_true",
        help="disable the explicitly selected HTTPS listener",
    )
    action.add_argument(
        "--status",
        action="store_true",
        help="show current Tailscale Serve status without changing it",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect current routes and print mutations without applying them",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.status:
            show_status()
        elif args.disable:
            if args.https_port is None:
                raise RuntimeError("--disable requires --https-port")
            disable(https_port=args.https_port, dry_run=args.dry_run)
        else:
            configure(
                backend=args.backend,
                https_port=args.https_port,
                force=args.force,
                dry_run=args.dry_run,
            )
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        geteuid = getattr(os, "geteuid", None)
        if platform.system() == "Linux" and callable(geteuid) and geteuid() != 0:
            print(
                "On Linux, retry with sudo if Tailscale reports a permissions error.",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
