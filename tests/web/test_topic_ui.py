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
    assert 'id="topic-search"\n        type="search"' in INDEX


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


def test_controls_are_kept_in_a_permanent_header() -> None:
    assert '<header id="app-header">' in INDEX
    assert "position: sticky; top: 0" in INDEX
    assert "overflow: hidden" in INDEX
    assert "min-height: 0; overflow-y: auto" in INDEX


def test_immersion_control_is_present() -> None:
    assert 'id="immersion-control"' in INDEX
    assert 'id="immersion" type="checkbox"' in INDEX
    assert 'document.getElementById("immersion")' in MAIN


def test_immersion_shows_the_last_two_consecutive_speaker_runs() -> None:
    assert "const transcriptSpeakerRuns" in MAIN
    assert "currentRun?.role === entry.role" in MAIN
    assert "currentRun.entries.push(entry)" in MAIN
    assert ".slice(-2)" in MAIN
    assert ".flatMap((run) => run.entries)" in MAIN


def test_topic_search_filters_the_complete_telegram_topic_list_locally() -> None:
    assert 'sendControl({ type: "list_topics", query: "", limit: 100 })' in MAIN
    assert "let availableTopics = []" in MAIN
    assert "const matchingTopics = () =>" in MAIN
    assert ".split(/\\s+/)" in MAIN
    assert "words.every((word) => title.includes(word))" in MAIN
    assert "availableTopics = Array.isArray(msg.topics) ? msg.topics : []" in MAIN
    assert "topicSearchTimer = setTimeout(() => applyTopicSearch(), 100)" in MAIN
    assert 'new Option("No matching topics", "")' in MAIN


def test_immersion_is_temporary_and_rerenders_without_storage() -> None:
    assert "immersionMode = els.immersion.checked" in MAIN
    assert "renderTranscript();" in MAIN
    assert "hv_immersion" not in MAIN
