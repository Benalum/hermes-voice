from hermes_voice.kit.sentences import split_sentences


class TestSplitSentences:
    def test_splits_on_sentence_punctuation(self) -> None:
        assert split_sentences("Hello there. How are you? Great!") == (
            "Hello there.",
            "How are you?",
            "Great!",
        )

    def test_single_sentence_without_terminator(self) -> None:
        assert split_sentences("just a fragment") == ("just a fragment",)

    def test_empty_and_whitespace_yield_nothing(self) -> None:
        assert split_sentences("") == ()
        assert split_sentences("   \n ") == ()

    def test_does_not_split_on_decimals(self) -> None:
        assert split_sentences("Pi is 3.14 roughly. Yes.") == ("Pi is 3.14 roughly.", "Yes.")

    def test_does_not_split_on_common_abbreviations(self) -> None:
        assert split_sentences("Talk to Dr. Smith today. Then rest.") == (
            "Talk to Dr. Smith today.",
            "Then rest.",
        )
        assert split_sentences("Use tools e.g. hammers. Done.") == (
            "Use tools e.g. hammers.",
            "Done.",
        )

    def test_newlines_separate_sentences(self) -> None:
        assert split_sentences("First point\nSecond point") == ("First point", "Second point")

    def test_collapses_internal_whitespace(self) -> None:
        assert split_sentences("Hello   there.  Bye.") == ("Hello there.", "Bye.")
