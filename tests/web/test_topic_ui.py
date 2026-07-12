"""Static browser contract checks for Telegram topic controls."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "hermes_voice" / "web" / "index.html").read_text()
MAIN = (ROOT / "hermes_voice" / "web" / "main.js").read_text()


def test_topic_controls_are_present_and_disabled_before_connection() -> None:
    assert 'id="topic-search"' in INDEX
    assert 'id="topic"' in INDEX
    assert 'id="refresh-topics"' in INDEX
    assert 'id="topic-status"' in INDEX
    assert 'id="topic-search"\n      type="search"' in INDEX


def test_browser_uses_topic_websocket_contract() -> None:
    assert 'type: "list_topics"' in MAIN
    assert 'type: "select_topic"' in MAIN
    assert 'case "topics":' in MAIN
    assert 'case "topic_selected":' in MAIN
    assert 'case "topic_history":' in MAIN


def test_microphone_audio_waits_for_selected_topic_history() -> None:
    assert "(!topicMode || topicReady)\n      && !muted" in MAIN
    assert "selectedTopicId = msg.topic_id" in MAIN
    assert "topicReady = true" in MAIN


def test_non_topic_modes_keep_the_existing_audio_path() -> None:
    assert "topicMode = options.length > 0" in MAIN
    assert "!topicMode || topicReady" in MAIN


def test_topic_history_is_temporary_browser_state() -> None:
    assert "renderHistory" in MAIN
    assert "clearTranscript" in MAIN
    assert "hv_topic" not in MAIN
    assert "indexedDB" not in MAIN
