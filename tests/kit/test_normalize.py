import hermes_voice.kit.normalize as normalize
from hermes_voice.kit.normalize import normalize_for_speech


class TestNormalizeForSpeech:
    def test_plain_text_passes_through(self) -> None:
        assert normalize_for_speech("Hello there.") == "Hello there."

    def test_strips_markdown_emphasis(self) -> None:
        assert normalize_for_speech("this is **bold** and *italic* and __underlined__") == (
            "this is bold and italic and underlined"
        )

    def test_strips_headers_and_bullets(self) -> None:
        assert normalize_for_speech("## Plan\n- first thing\n* second thing") == (
            "Plan. first thing. second thing"
        )

    def test_replaces_fenced_code_blocks(self) -> None:
        text = "Run this:\n```python\nprint('hi')\n```\nthen check."
        assert normalize_for_speech(text) == "Run this: (code block skipped) then check."

    def test_inline_code_keeps_content(self) -> None:
        assert normalize_for_speech("run `make test` now") == "run make test now"

    def test_markdown_link_speaks_label(self) -> None:
        assert normalize_for_speech("see [the docs](https://docs.python.org/3/)") == (
            "see the docs"
        )

    def test_bare_url_speaks_domain(self) -> None:
        assert normalize_for_speech("check https://github.com/foo/bar for details") == (
            "check (link to github.com) for details"
        )

    def test_collapses_whitespace(self) -> None:
        assert normalize_for_speech("a  b\n\n\nc") == "a b c"

    def test_caps_length_with_truncation_notice(self, monkeypatch) -> None:
        monkeypatch.setattr(normalize, "MAX_SPOKEN_CHARS", 1500)

        result = normalize_for_speech("word " * 1000)

        assert len(result) == 1500
        assert result.endswith("… message truncated, see Telegram")

    def test_zero_disables_truncation(self, monkeypatch) -> None:
        monkeypatch.setattr(normalize, "MAX_SPOKEN_CHARS", 0)

        result = normalize_for_speech("word " * 1000)

        assert len(result) > 1500
        assert "message truncated" not in result

    def test_environment_zero_disables_limit(self, monkeypatch) -> None:
        monkeypatch.setenv("HV_MAX_SPOKEN_CHARS", "0")

        assert normalize._read_max_spoken_chars() == 0

    def test_invalid_environment_uses_default(self, monkeypatch) -> None:
        monkeypatch.setenv("HV_MAX_SPOKEN_CHARS", "invalid")

        assert normalize._read_max_spoken_chars() == normalize.DEFAULT_MAX_SPOKEN_CHARS

    def test_empty_input_gives_empty_output(self) -> None:
        assert normalize_for_speech("") == ""
