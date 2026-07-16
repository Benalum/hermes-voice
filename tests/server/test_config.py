from pathlib import Path

import pytest

from hermes_voice.server.config import ChatConfig, ConfigError, load_config

VALID = """
token = "test-token-abcdefghijklmnopqrstuvwxyz0123456789"

[telegram]
api_id = 12345
api_hash = "abcdef"
session_path = "~/.hermes-voice/hermes.session"

[chats.hermes]
peer = "@my_hermes_bot"
label = "Hermes"

[chats.ops]
peer = -1001234567890
label = "Ops Agent"
max_wait_s = 300
"""


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body)
    return path


class TestLoadConfig:
    def test_parses_full_config(self, tmp_path: Path) -> None:
        config = load_config(write_config(tmp_path, VALID))
        assert config.token == "test-token-abcdefghijklmnopqrstuvwxyz0123456789"
        assert config.telegram.api_id == 12345
        assert config.telegram.api_hash == "abcdef"
        assert config.telegram.session_path == Path("~/.hermes-voice/hermes.session").expanduser()
        assert config.chats["hermes"] == ChatConfig(
            key="hermes", peer="@my_hermes_bot", label="Hermes", max_wait_s=180.0
        )
        assert config.chats["ops"].peer == -1001234567890
        assert config.chats["ops"].max_wait_s == 300.0

    def test_chat_order_is_preserved(self, tmp_path: Path) -> None:
        config = load_config(write_config(tmp_path, VALID))
        assert list(config.chats) == ["hermes", "ops"]

    def test_missing_file_raises_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="config file not found"):
            load_config(tmp_path / "nope.toml")

    def test_missing_telegram_section_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="telegram"):
            load_config(write_config(tmp_path, 'token = "x"\n[chats.a]\npeer = "@b"\nlabel = "B"'))

    def test_missing_chats_raises(self, tmp_path: Path) -> None:
        body = 'token = "x"\n[telegram]\napi_id = 1\napi_hash = "h"'
        with pytest.raises(ConfigError, match="at least one"):
            load_config(write_config(tmp_path, body))

    def test_chat_without_label_defaults_to_key(self, tmp_path: Path) -> None:
        body = VALID.replace('label = "Hermes"\n', "")
        config = load_config(write_config(tmp_path, body))
        assert config.chats["hermes"].label == "hermes"

    @pytest.mark.parametrize(
        "token",
        [None, "", "   ", "change-me", "too-short"],
    )
    def test_rejects_invalid_gateway_tokens(
        self,
        tmp_path: Path,
        token: str | None,
    ) -> None:
        token_line = "" if token is None else f'token = "{token}"\n'
        body = VALID.replace(
            'token = "test-token-abcdefghijklmnopqrstuvwxyz0123456789"\n',
            token_line,
            1,
        )

        with pytest.raises(ConfigError, match="token"):
            load_config(write_config(tmp_path, body))

    @pytest.mark.parametrize(
        "max_wait",
        ["-1", "0", "nan", "inf", "true"],
    )
    def test_rejects_invalid_max_wait(
        self,
        tmp_path: Path,
        max_wait: str,
    ) -> None:
        body = VALID.replace(
            "max_wait_s = 300",
            f"max_wait_s = {max_wait}",
        )

        with pytest.raises(
            ConfigError,
            match="max_wait_s",
        ):
            load_config(write_config(tmp_path, body))

    def test_rejects_non_table_chat(
        self,
        tmp_path: Path,
    ) -> None:
        body = """
        token = "test-token-abcdefghijklmnopqrstuvwxyz0123456789"
        chats = { hermes = 7 }

        [telegram]
        api_id = 12345
        api_hash = "abcdef"
        """

        with pytest.raises(
            ConfigError,
            match="TOML table",
        ):
            load_config(write_config(tmp_path, body))

    def test_rejects_boolean_peer(
        self,
        tmp_path: Path,
    ) -> None:
        body = VALID.replace(
            'peer = "@my_hermes_bot"',
            "peer = true",
            1,
        )

        with pytest.raises(ConfigError, match="peer"):
            load_config(write_config(tmp_path, body))
