"""Tests for spoken mute/unmute control."""

import pytest

from hermes_voice.kit.voice_mute import VoiceMuteControl


def test_mute_command_is_consumed_and_mutes() -> None:
    control = VoiceMuteControl()

    result = control.handle("Mute me.")

    assert result.forward is False
    assert result.status == "muted"
    assert control.muted is True


def test_ordinary_speech_is_dropped_while_muted() -> None:
    control = VoiceMuteControl(muted=True)

    result = control.handle("This private conversation must not be sent.")

    assert result.forward is False
    assert result.status is None
    assert control.muted is True


def test_unmute_command_is_consumed_and_unmutes() -> None:
    control = VoiceMuteControl(muted=True)

    result = control.handle("Start listening!")

    assert result.forward is False
    assert result.status == "unmuted"
    assert control.muted is False


def test_ordinary_speech_is_forwarded_while_unmuted() -> None:
    control = VoiceMuteControl()

    result = control.handle("What is on my calendar?")

    assert result.forward is True
    assert result.status is None
    assert control.muted is False


def test_unmute_word_inside_a_sentence_does_not_trigger() -> None:
    control = VoiceMuteControl(muted=True)

    result = control.handle("Explain how to unmute a microphone")

    assert result.forward is False
    assert result.status is None
    assert control.muted is True


def test_explicit_polite_commands_are_supported() -> None:
    control = VoiceMuteControl()

    muted = control.handle("Hey Hermes, please mute me.")
    assert muted.status == "muted"
    assert control.muted is True

    unmuted = control.handle("Hermes, can you start listening to me please?")
    assert unmuted.status == "unmuted"
    assert control.muted is False


def test_button_state_uses_the_same_authoritative_control() -> None:
    control = VoiceMuteControl()

    assert control.set_muted(True).status == "muted"
    assert control.handle("Private words stay here.").forward is False
    assert control.handle("Unmute me.").status == "unmuted"
    assert control.muted is False


def test_incidental_mute_phrase_does_not_toggle() -> None:
    control = VoiceMuteControl()

    result = control.handle("Explain why someone might say mute me in a tutorial.")

    assert result.forward is True
    assert result.status is None
    assert control.muted is False


@pytest.mark.parametrize(
    "command",
    (
        "Stop speech",
        "Hermes stop speaking",
        "Hey Hermes, please stop talking",
        "Be quiet please",
        "Cancel speech",
        "Hermes stop",
    ),
)
def test_stop_speech_commands_are_consumed_without_changing_mute(
    command: str,
) -> None:
    control = VoiceMuteControl(muted=True)

    result = control.handle(command)

    assert result.forward is False
    assert result.stop_speaking is True
    assert result.status is None
    assert control.muted is True


def test_incidental_stop_speech_phrase_is_not_a_command() -> None:
    control = VoiceMuteControl()

    result = control.handle("Explain why someone might say stop speaking in a tutorial")

    assert result.forward is True
    assert result.stop_speaking is False


def test_mute_myself_and_leading_filler_are_supported() -> None:
    control = VoiceMuteControl()

    result = control.handle("No, mute myself")

    assert result.status == "muted"
    assert control.muted is True


def test_unmute_my_self_is_supported() -> None:
    control = VoiceMuteControl(muted=True)

    result = control.handle("Hermes unmute my self")

    assert result.status == "unmuted"
    assert control.muted is False
