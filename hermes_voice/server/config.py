"""Load and validate ~/.hermes-voice/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.hermes-voice/config.toml")
DEFAULT_MAX_WAIT_S = 180.0


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class TelegramConfig:
    api_id: int
    api_hash: str
    session_path: Path


@dataclass(frozen=True)
class ChatConfig:
    key: str
    peer: str | int
    label: str
    max_wait_s: float


@dataclass(frozen=True)
class Config:
    token: str
    telegram: TelegramConfig
    chats: dict[str, ChatConfig]


def load_config(path: Path | None = None) -> Config:
    resolved = (path or DEFAULT_CONFIG_PATH).expanduser()
    if not resolved.is_file():
        raise ConfigError(f"config file not found: {resolved}")
    with resolved.open("rb") as fh:
        raw = tomllib.load(fh)

    telegram_raw = raw.get("telegram")
    if not isinstance(telegram_raw, dict):
        raise ConfigError("missing [telegram] section (api_id, api_hash)")
    try:
        telegram = TelegramConfig(
            api_id=int(telegram_raw["api_id"]),
            api_hash=str(telegram_raw["api_hash"]),
            session_path=Path(
                str(telegram_raw.get("session_path", "~/.hermes-voice/hermes.session"))
            ).expanduser(),
        )
    except KeyError as exc:
        raise ConfigError(f"missing telegram setting: {exc}") from exc

    chats_raw = raw.get("chats")
    if not isinstance(chats_raw, dict) or not chats_raw:
        raise ConfigError("config must define at least one [chats.<key>] entry")
    chats: dict[str, ChatConfig] = {}
    for key, chat_raw in chats_raw.items():
        if "peer" not in chat_raw:
            raise ConfigError(f"chat {key!r} is missing 'peer'")
        peer = chat_raw["peer"]
        if not isinstance(peer, str | int):
            raise ConfigError(f"chat {key!r} peer must be a string or chat id")
        chats[key] = ChatConfig(
            key=key,
            peer=peer,
            label=str(chat_raw.get("label", key)),
            max_wait_s=float(chat_raw.get("max_wait_s", DEFAULT_MAX_WAIT_S)),
        )

    return Config(token=str(raw.get("token", "")), telegram=telegram, chats=chats)
