from hermes_voice.kit.turns import BargeIn, SpeechEnd, SpeechStart, TurnConfig, TurnManager

FRAME = b"\x00" * 1024

CONFIG = TurnConfig(
    speech_threshold=0.5,
    barge_threshold=0.7,
    onset_frames=3,
    hangover_frames=16,
    barge_frames=8,
    pre_roll_frames=10,
)


def feed_frames(
    tm: TurnManager, probs: list[float], *, speaking: bool = False
) -> list[object]:
    events: list[object] = []
    for prob in probs:
        events.extend(tm.feed(FRAME, prob, speaking=speaking))
    return events


class TestSpeechStart:
    def test_sustained_speech_emits_speech_start(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.9, 0.9, 0.9])
        assert events == [SpeechStart()]

    def test_brief_blip_below_onset_frames_is_ignored(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.9, 0.9, 0.1, 0.9, 0.1])
        assert events == []

    def test_silence_emits_nothing(self) -> None:
        tm = TurnManager(CONFIG)
        assert feed_frames(tm, [0.1] * 50) == []


class TestSpeechEnd:
    def test_hangover_of_silence_ends_utterance(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.9] * 5 + [0.1] * 16)
        assert events[0] == SpeechStart()
        assert isinstance(events[1], SpeechEnd)

    def test_short_pause_does_not_end_utterance(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.9] * 5 + [0.1] * 15 + [0.9] * 2)
        assert events == [SpeechStart()]

    def test_utterance_pcm_includes_pre_roll_and_speech(self) -> None:
        tm = TurnManager(CONFIG)
        silence_frames = 4
        speech_frames = 5
        events = feed_frames(tm, [0.1] * silence_frames + [0.9] * speech_frames + [0.1] * 16)
        end = next(e for e in events if isinstance(e, SpeechEnd))
        # pre-roll (4 silent frames, fewer than pre_roll_frames) + speech + hangover
        expected_frames = silence_frames + speech_frames + 16
        assert len(end.pcm) == expected_frames * len(FRAME)

    def test_pre_roll_is_capped(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.1] * 100 + [0.9] * 5 + [0.1] * 16)
        end = next(e for e in events if isinstance(e, SpeechEnd))
        expected_frames = CONFIG.pre_roll_frames + 5 + 16
        assert len(end.pcm) == expected_frames * len(FRAME)

    def test_manager_resets_after_speech_end(self) -> None:
        tm = TurnManager(CONFIG)
        feed_frames(tm, [0.9] * 5 + [0.1] * 16)
        events = feed_frames(tm, [0.9, 0.9, 0.9])
        assert events == [SpeechStart()]


class TestBargeIn:
    def test_sustained_loud_speech_while_speaking_emits_barge_in(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.8] * 8, speaking=True)
        assert events == [BargeIn()]

    def test_normal_level_speech_while_speaking_is_suppressed(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.6] * 40, speaking=True)
        assert events == []

    def test_interrupted_loud_run_does_not_barge(self) -> None:
        tm = TurnManager(CONFIG)
        events = feed_frames(tm, [0.8] * 7 + [0.1] + [0.8] * 7, speaking=True)
        assert events == []

    def test_barge_frames_are_retained_in_next_utterance(self) -> None:
        tm = TurnManager(CONFIG)
        feed_frames(tm, [0.8] * 8, speaking=True)
        events = feed_frames(tm, [0.9] * 4 + [0.1] * 16)
        end = next(e for e in events if isinstance(e, SpeechEnd))
        expected_frames = 8 + 4 + 16
        assert len(end.pcm) == expected_frames * len(FRAME)

    def test_no_second_speech_start_after_barge_in(self) -> None:
        tm = TurnManager(CONFIG)
        feed_frames(tm, [0.8] * 8, speaking=True)
        events = feed_frames(tm, [0.9] * 4)
        assert events == []
