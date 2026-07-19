"""One-time interactive Telethon login. Run BEFORE enabling the launchd service:

    uv run python -m hermes_voice.scripts.login

Prompts for the phone-code Telegram sends you (and 2FA password if set), then
writes the session file referenced by ~/.hermes-voice/config.toml.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import stat
import sys
from typing import Any

from hermes_voice.server.config import Config, ConfigError, load_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorize the Hermes Voice Telegram session")
    parser.add_argument(
        "--qr",
        action="store_true",
        help="authorize by scanning a QR code from an existing Telegram mobile session",
    )
    return parser.parse_args()


async def _authorize_with_qr(client: Any) -> None:
    import qrcode
    from telethon.errors import SessionPasswordNeededError

    await client.connect()
    if await client.is_user_authorized():
        print("Telegram session is already authorized; QR login is not required.")
        return

    qr_login = await client.qr_login()
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_login.url)
    qr.make(fit=True)

    print("Open Telegram on your phone, then choose:")
    print("  Settings -> Devices -> Link Desktop Device")
    print("Scan this QR code before it expires:\n")
    qr.print_ascii(invert=True)

    try:
        await qr_login.wait()
    except SessionPasswordNeededError:
        password = getpass.getpass("Telegram two-step verification password: ")
        await client.sign_in(password=password)
    except TimeoutError:
        raise RuntimeError("QR code expired; run the command again for a new code") from None


async def _verify(config: Config, client: Any) -> None:
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (@{me.username}, id {me.id})")

    session_file = config.telegram.session_path.with_suffix(".session")
    if session_file.exists():
        session_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        print(f"Session saved to {session_file} (permissions 600)")

    print("Verifying configured chats resolve:")
    for key, chat in config.chats.items():
        try:
            entity = await client.get_entity(chat.peer)
            name = getattr(entity, "title", None) or getattr(entity, "first_name", chat.peer)
            print(f"  ✓ {key}: {name}")
        except Exception as exc:
            print(f"  ✗ {key}: {chat.peer!r} did not resolve ({exc})")


async def main(*, qr: bool = False) -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Copy config.example.toml to ~/.hermes-voice/config.toml first.", file=sys.stderr)
        return 1

    from telethon import TelegramClient

    session_path = config.telegram.session_path
    session_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    client = TelegramClient(str(session_path), config.telegram.api_id, config.telegram.api_hash)
    try:
        if qr:
            await _authorize_with_qr(client)
        else:
            await client.start()  # interactive: phone, code, optional 2FA password
        await _verify(config, client)
    finally:
        await client.disconnect()
    return 0


if __name__ == "__main__":
    args = _parse_args()
    raise SystemExit(asyncio.run(main(qr=args.qr)))
