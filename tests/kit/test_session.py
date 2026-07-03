from hermes_voice.kit.session import (
    AgentSpeakable,
    BargedIn,
    CancelPressed,
    ChatSelected,
    EnqueueSpeech,
    MaxWaitTimedOut,
    RelaySend,
    ResetReplies,
    SendAgentText,
    SendTranscript,
    Session,
    SpeechEnded,
    State,
    StopSpeaking,
    SttCompleted,
    Transcribe,
    TtsFinished,
    TurnSettled,
    advance,
)


def make(state: State, *, turn_open: bool = False, chat_key: str | None = "hermes") -> Session:
    return Session(state=state, turn_open=turn_open, chat_key=chat_key)


class TestChatBinding:
    def test_initial_session_is_idle_with_no_chat(self) -> None:
        session = Session.initial()
        assert session.state is State.IDLE
        assert session.chat_key is None

    def test_selecting_chat_from_idle_starts_listening(self) -> None:
        session, effects = advance(Session.initial(), ChatSelected(chat_key="hermes"))
        assert session == make(State.LISTENING)
        assert effects == (ResetReplies(chat_key="hermes"),)

    def test_switching_chat_while_speaking_stops_and_resets(self) -> None:
        session, effects = advance(
            make(State.SPEAKING, turn_open=True), ChatSelected(chat_key="ops")
        )
        assert session == make(State.LISTENING, chat_key="ops")
        assert effects == (StopSpeaking(), ResetReplies(chat_key="ops"))

    def test_events_in_idle_are_ignored(self) -> None:
        session, effects = advance(
            Session.initial(), SpeechEnded(pcm=b"x")
        )
        assert session == Session.initial()
        assert effects == ()


class TestUserUtterance:
    def test_speech_end_while_listening_starts_transcription(self) -> None:
        session, effects = advance(make(State.LISTENING), SpeechEnded(pcm=b"audio"))
        assert session == make(State.TRANSCRIBING)
        assert effects == (Transcribe(pcm=b"audio"),)

    def test_empty_transcript_returns_to_listening(self) -> None:
        session, effects = advance(make(State.TRANSCRIBING), SttCompleted(text="  "))
        assert session == make(State.LISTENING)
        assert effects == ()

    def test_transcript_is_relayed_and_waits_for_agent(self) -> None:
        session, effects = advance(make(State.TRANSCRIBING), SttCompleted(text="hello agent"))
        assert session == make(State.WAITING, turn_open=True)
        assert effects == (
            SendTranscript(text="hello agent"),
            RelaySend(text="hello agent"),
        )


class TestAgentReplies:
    def test_speakable_reply_while_waiting_starts_speaking(self) -> None:
        session, effects = advance(
            make(State.WAITING, turn_open=True), AgentSpeakable(text="On it.", message_id=7)
        )
        assert session == make(State.SPEAKING, turn_open=True)
        assert effects == (
            SendAgentText(text="On it.", message_id=7),
            EnqueueSpeech(text="On it."),
        )

    def test_additional_speakable_messages_queue_while_speaking(self) -> None:
        session, effects = advance(
            make(State.SPEAKING, turn_open=True), AgentSpeakable(text="More.", message_id=8)
        )
        assert session == make(State.SPEAKING, turn_open=True)
        assert effects == (
            SendAgentText(text="More.", message_id=8),
            EnqueueSpeech(text="More."),
        )

    def test_late_reply_while_listening_is_spoken(self) -> None:
        session, effects = advance(
            make(State.LISTENING), AgentSpeakable(text="Done!", message_id=9)
        )
        assert session == make(State.SPEAKING)
        assert effects == (
            SendAgentText(text="Done!", message_id=9),
            EnqueueSpeech(text="Done!"),
        )


class TestTurnCompletion:
    def test_settle_while_waiting_returns_to_listening(self) -> None:
        session, effects = advance(make(State.WAITING, turn_open=True), TurnSettled())
        assert session == make(State.LISTENING)
        assert effects == ()

    def test_settle_while_speaking_keeps_draining(self) -> None:
        session, effects = advance(make(State.SPEAKING, turn_open=True), TurnSettled())
        assert session == make(State.SPEAKING)
        assert effects == ()

    def test_tts_finished_after_settle_returns_to_listening(self) -> None:
        session, effects = advance(make(State.SPEAKING), TtsFinished())
        assert session == make(State.LISTENING)
        assert effects == ()

    def test_tts_finished_with_open_turn_returns_to_waiting(self) -> None:
        session, effects = advance(make(State.SPEAKING, turn_open=True), TtsFinished())
        assert session == make(State.WAITING, turn_open=True)
        assert effects == ()


class TestInterruptions:
    def test_barge_in_stops_speech_and_listens(self) -> None:
        session, effects = advance(make(State.SPEAKING, turn_open=True), BargedIn())
        assert session == make(State.LISTENING, turn_open=True)
        assert effects == (StopSpeaking(),)

    def test_cancel_while_speaking_with_open_turn_goes_to_waiting(self) -> None:
        session, effects = advance(make(State.SPEAKING, turn_open=True), CancelPressed())
        assert session == make(State.WAITING, turn_open=True)
        assert effects == (StopSpeaking(),)

    def test_cancel_while_speaking_with_settled_turn_listens(self) -> None:
        session, effects = advance(make(State.SPEAKING), CancelPressed())
        assert session == make(State.LISTENING)
        assert effects == (StopSpeaking(),)

    def test_cancel_while_listening_is_a_noop(self) -> None:
        session, effects = advance(make(State.LISTENING), CancelPressed())
        assert session == make(State.LISTENING)
        assert effects == ()


class TestFollowUpsAndTimeout:
    def test_follow_up_speech_while_waiting_transcribes(self) -> None:
        session, effects = advance(
            make(State.WAITING, turn_open=True), SpeechEnded(pcm=b"more")
        )
        assert session == make(State.TRANSCRIBING, turn_open=True)
        assert effects == (Transcribe(pcm=b"more"),)

    def test_follow_up_transcript_keeps_waiting(self) -> None:
        session, effects = advance(
            make(State.TRANSCRIBING, turn_open=True), SttCompleted(text="also this")
        )
        assert session == make(State.WAITING, turn_open=True)
        assert effects == (
            SendTranscript(text="also this"),
            RelaySend(text="also this"),
        )

    def test_max_wait_timeout_speaks_notice_and_closes_turn(self) -> None:
        session, effects = advance(make(State.WAITING, turn_open=True), MaxWaitTimedOut())
        assert session == make(State.SPEAKING)
        assert effects == (EnqueueSpeech(text="Still waiting on the agent."),)
