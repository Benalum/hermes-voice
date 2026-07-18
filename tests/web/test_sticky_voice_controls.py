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
    match = re.search(
        rf'<(?P<tag>[a-z]+)[^>]*id="{re.escape(element_id)}"'
        rf"[^>]*>.*?</(?P=tag)>",
        INDEX,
        flags=re.DOTALL,
    )
    assert match is not None, f"missing HTML element: {element_id}"
    return match.group(0)


def test_only_voice_action_strip_is_sticky() -> None:
    header = _css_rule("#app-header")
    voice_actions = _css_rule("#voice-actions")

    assert "position: sticky" not in header
    assert "position: fixed" not in header

    assert "position: sticky" in voice_actions
    assert "top: 0" in voice_actions


def test_voice_status_mute_and_stop_are_in_sticky_strip() -> None:
    controls = _html_element("controls")
    voice_actions = _html_element("voice-actions")

    assert 'id="start"' in controls
    assert 'id="state"' not in controls
    assert 'id="mute"' not in controls
    assert 'id="stop-speaking"' not in controls

    assert 'id="state"' in voice_actions
    assert 'role="status"' in voice_actions
    assert 'aria-live="polite"' in voice_actions
    assert 'id="mute"' in voice_actions
    assert 'id="stop-speaking"' in voice_actions


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


def test_mute_button_waits_for_server_acknowledgement() -> None:
    assert "const requestedState = !muted" in MAIN
    assert 'sendControl({ type: "mute", on: requestedState })' in MAIN
    assert "els.mute.disabled = true" in MAIN
