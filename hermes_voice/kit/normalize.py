"""Prepare agent message text for TTS: strip markdown, tame URLs, cap length."""

from __future__ import annotations

import re

MAX_SPOKEN_CHARS = 1500
_TRUNCATION_NOTICE = "… message truncated, see Telegram"

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://([^/\s]+)\S*")
_INLINE_CODE = re.compile(r"`([^`]*)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_UNDERLINE = re.compile(r"__(.+?)__")
_ITALIC = re.compile(r"\*(.+?)\*")
_BLOCK_MARKER = re.compile(r"^(#+|[-*+]|\d+[.)])\s+")
_ENDS_LIKE_SENTENCE = re.compile(r"[.!?:;…]$")


def _strip_inline_markup(text: str) -> str:
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _BARE_URL.sub(lambda m: f"(link to {m.group(1)})", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _BOLD.sub(r"\1", text)
    text = _UNDERLINE.sub(r"\1", text)
    return _ITALIC.sub(r"\1", text)


def _join_lines(lines: list[tuple[str, bool]]) -> str:
    result = ""
    previous_was_block = False
    for text, is_block in lines:
        if not result:
            result = text
        elif (is_block or previous_was_block) and not _ENDS_LIKE_SENTENCE.search(result):
            result = f"{result}. {text}"
        else:
            result = f"{result} {text}"
        previous_was_block = is_block
    return result


def normalize_for_speech(text: str) -> str:
    text = _FENCED_CODE.sub(" (code block skipped) ", text)
    text = _strip_inline_markup(text)

    lines: list[tuple[str, bool]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        without_marker = _BLOCK_MARKER.sub("", stripped)
        collapsed = " ".join(without_marker.split())
        if collapsed:
            lines.append((collapsed, without_marker != stripped))

    result = _join_lines(lines)
    if len(result) > MAX_SPOKEN_CHARS:
        result = result[: MAX_SPOKEN_CHARS - len(_TRUNCATION_NOTICE)] + _TRUNCATION_NOTICE
    return result
