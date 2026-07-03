import pytest

from hermes_voice.kit.protocol import (
    AgentText,
    Cancel,
    ErrorMsg,
    Hello,
    Mute,
    ProtocolError,
    Ready,
    SelectChat,
    SpeakStart,
    SpeakStop,
    StateMsg,
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
        assert encode_server_msg(SpeakStop(epoch=3)) == '{"type": "speak_stop", "epoch": 3}'

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
