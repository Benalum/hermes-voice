from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "hermes_voice" / "web"
INDEX = (WEB / "index.html").read_text()
MAIN = (WEB / "main.js").read_text()


def _css_rule(selector: str) -> str:
    match = re.search(
        rf"^\s*{re.escape(selector)}\s*\{{"
        rf"(?P<body>.*?)^\s*\}}",
        INDEX,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing CSS rule: {selector}"
    return match.group("body")


def _html_element(element_id: str) -> str:
    open_match = re.search(
        rf'<(?P<tag>[a-z]+)[^>]*id="{re.escape(element_id)}"',
        INDEX,
    )
    assert open_match is not None, f"missing HTML element: {element_id}"
    tag = open_match.group("tag")
    start = open_match.start()
    depth = 0
    i = INDEX.find(">", start) + 1
    while i < len(INDEX):
        next_open = INDEX.find(f"<{tag}", i)
        next_close = INDEX.find(f"</{tag}>", i)
        if next_open == -1 and next_close == -1:
            break
        if next_close == -1 or (next_open != -1 and next_open < next_close):
            depth += 1
            i = next_open + len(f"<{tag}")
        else:
            if depth == 0:
                return INDEX[start : next_close + len(f"</{tag}>")]
            depth -= 1
            i = next_close + len(f"</{tag}>")
    raise AssertionError(f"unbalanced element: {element_id}")


def test_only_voice_action_strip_is_sticky() -> None:
    header = _css_rule("#app-header")
    voice_actions = _css_rule("#voice-actions")

    assert "position: sticky" not in header
    assert "position: fixed" not in header

    assert "position: sticky" in voice_actions
    assert "top: 0" in voice_actions


def test_header_and_sticky_voice_controls_have_distinct_roles() -> None:
    controls = _html_element("controls")
    voice_actions = _html_element("voice-actions")

    assert 'id="start"' in controls
    assert 'id="chat"' in controls
    assert 'id="chat-search"' in controls
    assert 'id="chat-status"' in controls
    assert 'id="stop-speaking"' in controls
    assert 'id="state"' not in controls
    assert 'id="mute"' not in controls
    assert 'id="mute-indicator"' not in controls

    assert 'id="state"' in voice_actions
    assert 'role="status"' in voice_actions
    assert 'aria-live="polite"' in voice_actions
    assert 'id="mute-indicator"' in voice_actions
    assert 'id="topic-controls"' in voice_actions
    assert 'id="topic"' in voice_actions
    assert 'id="top-button"' in voice_actions
    assert 'id="stop-speaking"' not in voice_actions


def test_chat_discovery_loads_once_and_searches_the_local_full_list() -> None:
    assert 'sendControl({ type: "list_chats", query: "", limit: 500 })' in MAIN
    assert 'case "chats":' in MAIN
    assert "availableChats" in MAIN
    assert "matchingChats" in MAIN
    assert "chatSearchTimer = setTimeout(() => applyChatSearch(), 50)" in MAIN


def test_page_owns_scrolling_instead_of_transcript() -> None:
    body = _css_rule("body")
    transcript = _css_rule("#transcript")

    assert "overflow-y: auto" in body
    assert "overflow: visible" in transcript
    assert "overflow-y: auto" not in transcript
    assert "document.scrollingElement" in MAIN


def test_command_mute_keeps_microphone_frames_flowing_to_server() -> None:
    assert "&& !muted" not in MAIN
    assert 'case "mute_state":' in MAIN
    assert "muted = Boolean(msg.on)" in MAIN


def test_sticky_mute_indicator_waits_for_server_acknowledgement() -> None:
    assert "const requestedState = !muted" in MAIN
    assert 'sendControl({ type: "mute", on: requestedState })' in MAIN
    assert "els.muteIndicator.disabled = true" in MAIN
    assert "els.mute." not in MAIN
