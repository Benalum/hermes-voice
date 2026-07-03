from hermes_voice.kit.replies import ReplyAggregator, ReplyConfig, Settled, Speak

CONFIG = ReplyConfig(edit_settle_s=1.5, settle_s=2.5, typing_hold_s=6.0)


def make() -> ReplyAggregator:
    return ReplyAggregator(CONFIG)


class TestSingleReply:
    def test_message_becomes_speakable_after_edit_settle(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="hi there", now=1.0)
        assert agg.tick(now=1.4) == ()
        assert agg.tick(now=2.5) == (Speak(message_id=11, text="hi there"),)

    def test_turn_settles_after_quiet_period(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="hi", now=1.0)
        events = agg.tick(now=2.6)
        assert events == (Speak(message_id=11, text="hi"),)
        assert agg.tick(now=3.4) == ()
        assert agg.tick(now=3.6) == (Settled(),)

    def test_no_settle_without_any_agent_message(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        assert agg.tick(now=100.0) == ()

    def test_messages_before_anchor_are_ignored(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=5, text="old", now=1.0)
        assert agg.tick(now=100.0) == ()


class TestMultiMessageBurst:
    def test_newer_message_makes_older_speakable_immediately(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="first", now=1.0)
        agg.on_agent_message(message_id=12, text="second", now=1.5)
        assert agg.tick(now=1.6) == (Speak(message_id=11, text="first"),)
        assert agg.tick(now=3.1) == (Speak(message_id=12, text="second"),)

    def test_settle_only_after_last_activity_quiets(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="first", now=1.0)
        agg.on_agent_message(message_id=12, text="second", now=2.0)
        agg.tick(now=3.6)
        assert agg.tick(now=4.4) == ()
        assert agg.tick(now=4.6) == (Settled(),)

    def test_speak_events_come_in_message_id_order(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=12, text="b", now=1.0)
        agg.on_agent_message(message_id=11, text="a", now=1.0)
        events = agg.tick(now=3.0)
        assert events == (
            Speak(message_id=11, text="a"),
            Speak(message_id=12, text="b"),
        )


class TestEditStreaming:
    def test_edits_delay_speakability_and_update_text(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="partial", now=1.0)
        agg.on_agent_edit(message_id=11, text="partial plus more", now=2.0)
        assert agg.tick(now=2.6) == ()
        assert agg.tick(now=3.6) == (Speak(message_id=11, text="partial plus more"),)

    def test_edits_to_spoken_messages_are_ignored(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="done", now=1.0)
        agg.tick(now=2.6)
        agg.on_agent_edit(message_id=11, text="rewritten", now=3.0)
        events = agg.tick(now=10.0)
        assert not any(isinstance(e, Speak) for e in events)

    def test_edits_extend_the_settle_window(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="v1", now=1.0)
        agg.on_agent_edit(message_id=11, text="v2", now=3.0)
        assert not any(isinstance(e, Settled) for e in agg.tick(now=4.6))
        assert Settled() in agg.tick(now=5.6)


class TestTypingHold:
    def test_typing_defers_settlement(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="part one", now=1.0)
        agg.tick(now=2.6)
        agg.on_typing(now=3.0)
        assert agg.tick(now=5.0) == ()
        assert agg.tick(now=9.1) == (Settled(),)

    def test_message_after_typing_still_speaks(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="one", now=1.0)
        agg.tick(now=2.6)
        agg.on_typing(now=3.0)
        agg.on_agent_message(message_id=12, text="two", now=4.0)
        assert agg.tick(now=5.6) == (Speak(message_id=12, text="two"),)


class TestLateAndFollowUp:
    def test_late_message_after_settle_still_speaks(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="hi", now=1.0)
        agg.tick(now=2.6)
        assert agg.tick(now=3.6) == (Settled(),)
        agg.on_agent_message(message_id=13, text="ps: one more thing", now=60.0)
        assert agg.tick(now=61.6) == (Speak(message_id=13, text="ps: one more thing"),)

    def test_no_second_settle_after_late_message(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="hi", now=1.0)
        agg.tick(now=2.6)
        agg.tick(now=3.6)
        agg.on_agent_message(message_id=13, text="ps", now=60.0)
        agg.tick(now=61.6)
        assert not any(isinstance(e, Settled) for e in agg.tick(now=100.0))

    def test_follow_up_anchor_keeps_turn_open(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="working on it", now=1.0)
        agg.anchor(message_id=14, now=2.0)
        agg.tick(now=3.0)
        agg.on_agent_message(message_id=15, text="both done", now=4.0)
        events = agg.tick(now=5.6)
        assert Speak(message_id=15, text="both done") in events

    def test_reset_forgets_everything(self) -> None:
        agg = make()
        agg.anchor(message_id=10, now=0.0)
        agg.on_agent_message(message_id=11, text="hi", now=1.0)
        agg.reset()
        assert agg.tick(now=10.0) == ()
