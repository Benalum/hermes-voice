"""One-time interactive Telethon login. Run BEFORE enabling the launchd service:

    uv run python -m hermes_voice.scripts.login

Prompts for the phone-code Telegram sends you (and 2FA password if set), then
writes the session file referenced by ~/.hermes-voice/config.toml.
"""

from __future__ import annotations

import asyncio
import stat
import sys

from hermes_voice.server.config import ConfigError, load_config


async def main() -> int:
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
    await client.start()  # interactive: phone, code, optional 2FA password
    me = await client.get_me()
    print(f"Logged in as {me.first_name} (@{me.username}, id {me.id})")

    session_file = session_path.with_suffix(".session")
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

    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
