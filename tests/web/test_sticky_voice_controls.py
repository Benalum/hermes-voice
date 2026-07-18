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
    # Locate the element's opening tag, then walk forward counting nested
    # <div>…</div> pairs (the structure contains nested divs) so we capture the
    # full element including any nested children.
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
        nxt_open = INDEX.find(f"<{tag}", i)
        nxt_close = INDEX.find(f"</{tag}>", i)
        # No more tags of this kind => stop (shouldn't happen on valid HTML).
        if nxt_open == -1 and nxt_close == -1:
            break
        if nxt_close == -1 or (nxt_open != -1 and nxt_open < nxt_close):
            depth += 1
            i = nxt_open + len(f"<{tag}")
        else:
            if depth == 0:
                end = nxt_close + len(f"</{tag}>")
                return INDEX[start:end]
            depth -= 1
            i = nxt_close + len(f"</{tag}>")
    raise AssertionError(f"unbalanced element: {element_id}")


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

    # Mute + Stop Speech now live in the header controls next to Start.
    assert 'id="start"' in controls
    assert 'id="mute"' in controls
    assert 'id="stop-speaking"' in controls
    assert 'id="state"' not in controls

    # The sticky strip keeps the live state pill + topic controls + Top button
    # + a muted/unmuted indicator so the user can see mic state while scrolled.
    assert 'id="state"' in voice_actions
    assert 'role="status"' in voice_actions
    assert 'aria-live="polite"' in voice_actions
    assert 'id="topic-controls"' in voice_actions
    assert 'id="topic"' in voice_actions
    assert 'id="top-button"' in voice_actions
    assert 'id="mute-indicator"' in voice_actions


def test_chat_search_lives_in_header_and_requests_discovery() -> None:
    controls = _html_element("controls")
    # The chat search input + status live in the header controls next to the
    # chat selector, so the user can pull their Telegram chats without scrolling.
    assert 'id="chat"' in controls
    assert 'id="chat-search"' in controls
    assert 'id="chat-status"' in controls

    main = (WEB / "main.js").read_text()
    assert 'sendControl({ type: "list_chats", query' in main
    assert "requestChats(" in main
    assert "availableChats" in main
    assert 'case "chats":' in main
    # The sticky indicator must reflect the server's mute_state so the user
    # is always aware of mic state without scrolling to the header button.
    main = (WEB / "main.js").read_text()
    assert 'case "mute_state":' in main
    assert 'els.muteIndicator.textContent = muted ? "Muted" : "Unmuted"' in main
    assert 'els.muteIndicator.dataset.muted = String(muted)' in main
    # Clicking the indicator toggles mute (same path as the header button).
    assert "els.muteIndicator.onclick" in main
    assert 'sendControl({ type: "mute", on: requestedState })' in main


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
    assert 'muted = Boolean(msg.on)' in MAIN


def test_mute_button_waits_for_server_acknowledgement() -> None:
    assert "const requestedState = !muted" in MAIN
    assert 'sendControl({ type: "mute", on: requestedState })' in MAIN
    assert 'els.mute.disabled = true' in MAIN
