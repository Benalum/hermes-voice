"""Load and validate ~/.hermes-voice/config.toml."""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field

from hermes_voice.kit.speaker_gate import SpeakerGateConfig
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("~/.hermes-voice/config.toml")
DEFAULT_MAX_WAIT_S = 180.0
MIN_GATEWAY_TOKEN_BYTES = 32

_PLACEHOLDER_TOKENS = {
    "change-me",
    "changeme",
    "replace-me",
    "replace-this",
    "your-token-here",
}


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
    speaker_gate: SpeakerGateConfig = field(default_factory=SpeakerGateConfig)


def _require_gateway_token(value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError("token must be a string")

    if not value or not value.strip():
        raise ConfigError("token must not be empty or whitespace")

    if value != value.strip():
        raise ConfigError("token must not contain leading or trailing whitespace")

    if value.casefold() in _PLACEHOLDER_TOKENS:
        raise ConfigError("token is still set to a placeholder value")

    if len(value.encode("utf-8")) < MIN_GATEWAY_TOKEN_BYTES:
        raise ConfigError(
            f"token must contain at least {MIN_GATEWAY_TOKEN_BYTES} bytes; "
            "generate one with: "
            "python -c 'import secrets; "
            "print(secrets.token_urlsafe(32))'"
        )

    return value


def _require_api_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError("telegram api_id must be a positive integer")

    return value


def _require_nonempty_string(
    value: Any,
    *,
    setting: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{setting} must be a non-empty string")

    return value


def _require_peer(
    value: Any,
    *,
    chat_key: str,
) -> str | int:
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise ConfigError(f"chat {chat_key!r} peer must be a string or chat id")

    if isinstance(value, str) and not value.strip():
        raise ConfigError(f"chat {chat_key!r} peer must not be empty")

    return value


def _require_max_wait(
    value: Any,
    *,
    chat_key: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"chat {chat_key!r} max_wait_s must be a positive number")

    resolved = float(value)

    if not math.isfinite(resolved) or resolved <= 0:
        raise ConfigError(f"chat {chat_key!r} max_wait_s must be a finite positive number")

    return resolved


def validate_config(config: Config) -> Config:
    """Validate an already constructed or injected Config."""
    _require_gateway_token(config.token)
    _require_api_id(config.telegram.api_id)

    _require_nonempty_string(
        config.telegram.api_hash,
        setting="telegram api_hash",
    )

    if not isinstance(config.telegram.session_path, Path):
        raise ConfigError("telegram session_path must be a pathlib.Path")

    if not config.chats:
        raise ConfigError("config must define at least one chat")

    for key, chat in config.chats.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigError("chat keys must be non-empty strings")

        if chat.key != key:
            raise ConfigError(f"chat mapping key {key!r} does not match chat.key {chat.key!r}")

        _require_peer(
            chat.peer,
            chat_key=key,
        )

        _require_nonempty_string(
            chat.label,
            setting=f"chat {key!r} label",
        )

        _require_max_wait(
            chat.max_wait_s,
            chat_key=key,
        )

    return config


def load_config(path: Path | None = None) -> Config:
    resolved = (path or DEFAULT_CONFIG_PATH).expanduser()

    if not resolved.is_file():
        raise ConfigError(f"config file not found: {resolved}")

    try:
        with resolved.open("rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not parse config file {resolved}: {exc}") from exc

    telegram_raw = raw.get("telegram")

    if not isinstance(telegram_raw, dict):
        raise ConfigError("missing [telegram] section (api_id, api_hash)")

    if "api_id" not in telegram_raw:
        raise ConfigError("missing telegram setting: api_id")

    if "api_hash" not in telegram_raw:
        raise ConfigError("missing telegram setting: api_hash")

    session_path_raw = telegram_raw.get(
        "session_path",
        "~/.hermes-voice/hermes.session",
    )

    session_path = Path(
        _require_nonempty_string(
            session_path_raw,
            setting="telegram session_path",
        )
    ).expanduser()

    telegram = TelegramConfig(
        api_id=_require_api_id(telegram_raw["api_id"]),
        api_hash=_require_nonempty_string(
            telegram_raw["api_hash"],
            setting="telegram api_hash",
        ),
        session_path=session_path,
    )

    chats_raw = raw.get("chats")

    if not isinstance(chats_raw, dict) or not chats_raw:
        raise ConfigError("config must define at least one [chats.<key>] entry")

    chats: dict[str, ChatConfig] = {}

    for key, chat_raw in chats_raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigError("chat keys must be non-empty strings")

        if not isinstance(chat_raw, dict):
            raise ConfigError(f"chat {key!r} must be a TOML table")

        if "peer" not in chat_raw:
            raise ConfigError(f"chat {key!r} is missing 'peer'")

        label_raw = chat_raw.get("label", key)

        chats[key] = ChatConfig(
            key=key,
            peer=_require_peer(
                chat_raw["peer"],
                chat_key=key,
            ),
            label=_require_nonempty_string(
                label_raw,
                setting=f"chat {key!r} label",
            ),
            max_wait_s=_require_max_wait(
                chat_raw.get(
                    "max_wait_s",
                    DEFAULT_MAX_WAIT_S,
                ),
                chat_key=key,
            ),
        )

    return validate_config(
        Config(
            token=_require_gateway_token(raw.get("token")),
            telegram=telegram,
            chats=chats,
            speaker_gate=SpeakerGateConfig.from_section(raw.get("speaker_gate")),
        )
    )
