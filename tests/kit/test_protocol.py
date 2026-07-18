import pytest

from hermes_voice.kit.protocol import (
    AgentText,
    Cancel,
    Chats,
    ErrorMsg,
    Hello,
    ListChats,
    ListTopics,
    Mute,
    MuteState,
    ProtocolError,
    Ready,
    SelectChat,
    SelectTopic,
    SpeakStart,
    SpeakStop,
    StateMsg,
    TopicHistory,
    Topics,
    TopicSelected,
    Transcript,
    decode_audio_frame,
    decode_client_text,
    encode_audio_frame,
    encode_server_msg,
)


class TestClientMessages:
    def test_decodes_hello_with_token(self) -> None:
        msg = decode_client_text('{"type": "hello", "token": "s3cret"}')
        assert msg == Hello(token="s3cret")

    def test_decodes_select_chat(self) -> None:
        msg = decode_client_text('{"type": "select_chat", "chat_key": "research"}')
        assert msg == SelectChat(chat_key="research")

    def test_decodes_list_chats_with_full_discovery_limit(self) -> None:
        assert decode_client_text('{"type": "list_chats"}') == ListChats()
        assert decode_client_text(
            '{"type": "list_chats", "query": "  alex  ", "limit": 500}'
        ) == ListChats(query="alex", limit=500)

    def test_rejects_invalid_list_chats_values(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "list_chats", "limit": 0}')
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "list_chats", "limit": 501}')

    def test_decodes_list_topics_with_defaults_and_search(self) -> None:
        assert decode_client_text('{"type": "list_topics"}') == ListTopics()
        assert decode_client_text(
            '{"type": "list_topics", "query": "  system  ", "limit": 20}'
        ) == ListTopics(query="system", limit=20)

    def test_decodes_select_topic_with_history_limit(self) -> None:
        assert decode_client_text('{"type": "select_topic", "topic_id": 98}') == SelectTopic(
            topic_id=98
        )
        assert decode_client_text(
            '{"type": "select_topic", "topic_id": 98, "history_limit": 25}'
        ) == SelectTopic(topic_id=98, history_limit=25)

    def test_rejects_invalid_topic_request_values(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "list_topics", "limit": 0}')
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "select_topic", "topic_id": 0}')
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "select_topic", "topic_id": 98, "history_limit": 101}')

    def test_decodes_mute_on_and_off(self) -> None:
        assert decode_client_text('{"type": "mute", "on": true}') == Mute(on=True)
        assert decode_client_text('{"type": "mute", "on": false}') == Mute(on=False)

    def test_decodes_cancel(self) -> None:
        assert decode_client_text('{"type": "cancel"}') == Cancel()

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "reboot"}')

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text("not json")

    def test_rejects_missing_required_field(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "hello"}')

    def test_rejects_wrong_field_type(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text('{"type": "mute", "on": "yes"}')

    def test_rejects_non_object_json(self) -> None:
        with pytest.raises(ProtocolError):
            decode_client_text('["hello"]')


class TestServerMessages:
    def test_encodes_ready_with_chat_list(self) -> None:
        msg = Ready(
            chats=({"key": "research", "label": "Research"},),
            active_chat="research",
        )
        assert encode_server_msg(msg) == (
            '{"type": "ready", "chats": [{"key": "research", "label": "Research"}],'
            ' "active_chat": "research"}'
        )

    def test_encodes_authoritative_mute_state(self) -> None:
        assert encode_server_msg(MuteState(on=True, source="voice")) == (
            '{"type": "mute_state", "on": true, "source": "voice"}'
        )
        assert encode_server_msg(MuteState(on=False, source="button")) == (
            '{"type": "mute_state", "on": false, "source": "button"}'
        )

    def test_encodes_discovered_chats(self) -> None:
        msg = Chats(
            items=(
                {"key": "100123", "label": "Alex", "kind": "user"},
                {"key": "research", "label": "Research", "kind": "channel"},
            )
        )
        assert encode_server_msg(msg) == (
            '{"type": "chats", "chats": [{"key": "100123", "label": "Alex", '
            '"kind": "user"}, {"key": "research", "label": "Research", '
            '"kind": "channel"}]}'
        )

    def test_encodes_topics(self) -> None:
        msg = Topics(
            items=(
                {
                    "topic_id": 98,
                    "title": "System",
                    "top_message_id": 110,
                    "closed": False,
                    "pinned": False,
                },
            )
        )
        assert encode_server_msg(msg) == (
            '{"type": "topics", "topics": [{"topic_id": 98, "title": "System", '
            '"top_message_id": 110, "closed": false, "pinned": false}]}'
        )

    def test_encodes_topic_selection_and_history(self) -> None:
        assert encode_server_msg(TopicSelected(topic_id=98)) == (
            '{"type": "topic_selected", "topic_id": 98}'
        )
        history = TopicHistory(
            topic_id=98,
            messages=(
                {
                    "message_id": 109,
                    "topic_id": 98,
                    "role": "user",
                    "text": "Hello",
                    "has_attachment": False,
                    "date": "2026-07-12T04:00:00+00:00",
                },
            ),
        )
        assert encode_server_msg(history) == (
            '{"type": "topic_history", "topic_id": 98, "messages": '
            '[{"message_id": 109, "topic_id": 98, "role": "user", '
            '"text": "Hello", "has_attachment": false, '
            '"date": "2026-07-12T04:00:00+00:00"}]}'
        )

    def test_encodes_state(self) -> None:
        assert encode_server_msg(StateMsg(name="listening")) == (
            '{"type": "state", "name": "listening"}'
        )

    def test_encodes_user_transcript(self) -> None:
        msg = Transcript(role="user", text="hello there", final=True)
        assert encode_server_msg(msg) == (
            '{"type": "transcript", "role": "user", "text": "hello there", "final": true}'
        )

    def test_encodes_agent_text(self) -> None:
        msg = AgentText(text="On it.", message_id=42)
        assert encode_server_msg(msg) == (
            '{"type": "agent_text", "text": "On it.", "message_id": 42}'
        )

    def test_encodes_speak_start_and_stop(self) -> None:
        assert encode_server_msg(SpeakStart(epoch=3, sample_rate=24000)) == (
            '{"type": "speak_start", "epoch": 3, "sample_rate": 24000}'
        )
        assert encode_server_msg(SpeakStop(epoch=3)) == (
            '{"type": "speak_stop", "epoch": 3, "flush": false}'
        )
        assert encode_server_msg(SpeakStop(epoch=3, flush=True)) == (
            '{"type": "speak_stop", "epoch": 3, "flush": true}'
        )

    def test_encodes_error(self) -> None:
        assert encode_server_msg(ErrorMsg(message="boom")) == (
            '{"type": "error", "message": "boom"}'
        )


class TestAudioFrames:
    def test_round_trips_epoch_and_pcm(self) -> None:
        pcm = bytes(range(16))
        framed = encode_audio_frame(epoch=7, pcm=pcm)
        assert decode_audio_frame(framed) == (7, pcm)

    def test_epoch_prefix_is_4_bytes_little_endian(self) -> None:
        framed = encode_audio_frame(epoch=0x01020304, pcm=b"")
        assert framed == bytes([0x04, 0x03, 0x02, 0x01])

    def test_decode_rejects_frame_shorter_than_prefix(self) -> None:
        with pytest.raises(ProtocolError):
            decode_audio_frame(b"\x00\x01")

    def test_large_epoch_wraps_are_rejected(self) -> None:
        with pytest.raises(ProtocolError):
            encode_audio_frame(epoch=2**32, pcm=b"")
