from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hermes_voice.study.curriculum import (
    Curriculum,
    CurriculumCourse,
    CurriculumDeck,
    MasterySnapshot,
    ReviewCandidate,
    build_cumulative_review,
    course_unlock_decision,
    deck_unlock_decision,
    foundation_curriculum_skeleton,
)


def test_foundation_curriculum_is_ordered_and_chained() -> None:
    curriculum = foundation_curriculum_skeleton()

    assert curriculum.key == "mcat-medical-foundations-phase-1"
    assert len(curriculum.courses) == 22
    assert curriculum.ordered_courses()[0].name == "Learning and Scientific Reasoning"
    assert curriculum.ordered_courses()[-1].name == "Integrated Foundation Review"

    decks = curriculum.ordered_decks()
    assert len(decks) == 22
    assert decks[0].prerequisite_keys == ()
    assert decks[1].prerequisite_keys == (decks[0].key,)
    assert decks[-1].checkpoint is True


def test_curriculum_rejects_unknown_prerequisite() -> None:
    with pytest.raises(ValueError, match="unknown prerequisites"):
        Curriculum(
            key="bad",
            name="Bad",
            version="1",
            courses=(
                CurriculumCourse(
                    key="course",
                    name="Course",
                    order=0,
                    decks=(
                        CurriculumDeck(
                            key="deck",
                            name="Deck",
                            order=0,
                            prerequisite_keys=("missing",),
                        ),
                    ),
                ),
            ),
        )


def test_mastery_requires_quality_and_coverage() -> None:
    partial = MasterySnapshot(good=1, total_cards=10)
    complete = MasterySnapshot(good=8, hard=2, total_cards=10)

    assert partial.mastery == pytest.approx(0.1)
    assert complete.mastery == pytest.approx(0.9)


def test_deck_unlock_explains_missing_mastery() -> None:
    deck = CurriculumDeck(
        key="next",
        name="Next",
        order=1,
        prerequisite_keys=("first",),
        unlock_mastery=0.70,
    )

    locked = deck_unlock_decision(
        deck,
        {"first": MasterySnapshot(good=5, again=5, total_cards=10)},
    )
    unlocked = deck_unlock_decision(
        deck,
        {"first": MasterySnapshot(good=8, hard=2, total_cards=10)},
    )

    assert locked.unlocked is False
    assert "70% mastery" in locked.reasons[0]
    assert unlocked.unlocked is True


def test_course_unlock_uses_prerequisite_course_mastery() -> None:
    curriculum = foundation_curriculum_skeleton()
    first, second = curriculum.ordered_courses()[:2]
    first_deck = first.decks[0]

    locked = course_unlock_decision(second, curriculum, {})
    unlocked = course_unlock_decision(
        second,
        curriculum,
        {first_deck.key: MasterySnapshot(good=10, total_cards=10)},
    )

    assert locked.unlocked is False
    assert unlocked.unlocked is True


def test_cumulative_review_prioritizes_due_and_weak_cards() -> None:
    now = datetime(2026, 7, 21, 18, 0, tzinfo=UTC)
    candidates = [
        ReviewCandidate(1, "a", now - timedelta(days=3), 0.8),
        ReviewCandidate(2, "a", now - timedelta(days=1), 0.3, lapses=2),
        ReviewCandidate(3, "b", now + timedelta(days=1), 0.2, lapses=1),
        ReviewCandidate(4, "b", None, 0.9, newly_unlocked=True),
        ReviewCandidate(5, "c", None, 0.6, image_card=True),
    ]

    plan = build_cumulative_review(candidates, limit=4, now=now)

    assert plan.card_ids[:2] == (1, 2)
    assert 3 in plan.card_ids
    assert 5 in plan.card_ids
    assert len(plan.card_ids) == len(set(plan.card_ids))
    assert plan.overdue_count == 2
    assert plan.image_count >= 1


def test_cumulative_review_requires_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        build_cumulative_review([], limit=0)
