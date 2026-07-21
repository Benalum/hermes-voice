"""Curriculum ordering, progression, mastery, and cumulative review selection.

This module is deliberately storage-agnostic.  The SQLite StudyStore can persist
these records without coupling curriculum policy to a particular schema version.
Existing user-created decks remain unrestricted unless they are explicitly placed
inside a curriculum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable, Literal, Mapping, Sequence

ReviewRating = Literal["again", "hard", "good", "easy", "skipped"]


@dataclass(frozen=True, slots=True)
class CurriculumDeck:
    key: str
    name: str
    order: int
    prerequisite_keys: tuple[str, ...] = ()
    unlock_mastery: float = 0.70
    completion_mastery: float = 0.80
    checkpoint: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.name.strip():
            raise ValueError("curriculum deck key and name are required")
        if not 0.0 <= self.unlock_mastery <= 1.0:
            raise ValueError("unlock_mastery must be between zero and one")
        if not 0.0 <= self.completion_mastery <= 1.0:
            raise ValueError("completion_mastery must be between zero and one")


@dataclass(frozen=True, slots=True)
class CurriculumCourse:
    key: str
    name: str
    order: int
    decks: tuple[CurriculumDeck, ...]
    prerequisite_course_keys: tuple[str, ...] = ()
    completion_mastery: float = 0.80

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.name.strip():
            raise ValueError("course key and name are required")
        if not self.decks:
            raise ValueError("a curriculum course must contain at least one deck")
        if not 0.0 <= self.completion_mastery <= 1.0:
            raise ValueError("completion_mastery must be between zero and one")
        deck_keys = [deck.key for deck in self.decks]
        if len(deck_keys) != len(set(deck_keys)):
            raise ValueError(f"duplicate deck key in course {self.key}")


@dataclass(frozen=True, slots=True)
class Curriculum:
    key: str
    name: str
    version: str
    courses: tuple[CurriculumCourse, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.name.strip() or not self.version.strip():
            raise ValueError("curriculum key, name, and version are required")
        if not self.courses:
            raise ValueError("a curriculum must contain at least one course")
        course_keys = [course.key for course in self.courses]
        if len(course_keys) != len(set(course_keys)):
            raise ValueError("duplicate course key")
        all_decks = [deck.key for course in self.courses for deck in course.decks]
        if len(all_decks) != len(set(all_decks)):
            raise ValueError("deck keys must be unique across a curriculum")
        self._validate_references()

    def _validate_references(self) -> None:
        course_keys = {course.key for course in self.courses}
        deck_keys = {deck.key for course in self.courses for deck in course.decks}
        for course in self.courses:
            missing_courses = set(course.prerequisite_course_keys) - course_keys
            if missing_courses:
                raise ValueError(
                    f"course {course.key} has unknown prerequisites: {sorted(missing_courses)}"
                )
            for deck in course.decks:
                missing_decks = set(deck.prerequisite_keys) - deck_keys
                if missing_decks:
                    raise ValueError(
                        f"deck {deck.key} has unknown prerequisites: {sorted(missing_decks)}"
                    )

    def ordered_courses(self) -> tuple[CurriculumCourse, ...]:
        return tuple(sorted(self.courses, key=lambda item: (item.order, item.key)))

    def ordered_decks(self) -> tuple[CurriculumDeck, ...]:
        return tuple(
            deck
            for course in self.ordered_courses()
            for deck in sorted(course.decks, key=lambda item: (item.order, item.key))
        )


@dataclass(frozen=True, slots=True)
class MasterySnapshot:
    attempts: int = 0
    again: int = 0
    hard: int = 0
    good: int = 0
    easy: int = 0
    skipped: int = 0
    due_cards: int = 0
    total_cards: int = 0

    @property
    def reviewed(self) -> int:
        return self.again + self.hard + self.good + self.easy

    @property
    def mastery(self) -> float:
        """Return a conservative zero-to-one mastery score.

        Good and easy answers count fully, hard answers count partially, and
        again answers count zero.  Coverage prevents a learner from unlocking a
        deck after answering only one easy card correctly.
        """

        if self.total_cards <= 0 or self.reviewed <= 0:
            return 0.0
        quality = (self.good + self.easy + (0.5 * self.hard)) / self.reviewed
        coverage = min(1.0, self.reviewed / self.total_cards)
        return quality * coverage


@dataclass(frozen=True, slots=True)
class UnlockDecision:
    unlocked: bool
    reasons: tuple[str, ...] = ()


def deck_unlock_decision(
    deck: CurriculumDeck,
    mastery_by_deck: Mapping[str, MasterySnapshot],
) -> UnlockDecision:
    reasons: list[str] = []
    for prerequisite in deck.prerequisite_keys:
        snapshot = mastery_by_deck.get(prerequisite, MasterySnapshot())
        if snapshot.mastery < deck.unlock_mastery:
            reasons.append(
                f"Complete {prerequisite} to {deck.unlock_mastery:.0%} mastery "
                f"(currently {snapshot.mastery:.0%})."
            )
    return UnlockDecision(unlocked=not reasons, reasons=tuple(reasons))


def completed_deck(
    deck: CurriculumDeck,
    mastery_by_deck: Mapping[str, MasterySnapshot],
) -> bool:
    return mastery_by_deck.get(deck.key, MasterySnapshot()).mastery >= deck.completion_mastery


def course_mastery(
    course: CurriculumCourse,
    mastery_by_deck: Mapping[str, MasterySnapshot],
) -> float:
    values = [mastery_by_deck.get(deck.key, MasterySnapshot()).mastery for deck in course.decks]
    return sum(values) / len(values)


def course_unlock_decision(
    course: CurriculumCourse,
    curriculum: Curriculum,
    mastery_by_deck: Mapping[str, MasterySnapshot],
) -> UnlockDecision:
    courses = {item.key: item for item in curriculum.courses}
    reasons: list[str] = []
    for prerequisite_key in course.prerequisite_course_keys:
        prerequisite = courses[prerequisite_key]
        mastery = course_mastery(prerequisite, mastery_by_deck)
        if mastery < prerequisite.completion_mastery:
            reasons.append(
                f"Complete {prerequisite.name} to {prerequisite.completion_mastery:.0%} "
                f"mastery (currently {mastery:.0%})."
            )
    return UnlockDecision(unlocked=not reasons, reasons=tuple(reasons))


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    card_id: int
    deck_key: str
    due_at: datetime | None
    mastery: float
    lapses: int = 0
    last_reviewed_at: datetime | None = None
    newly_unlocked: bool = False
    image_card: bool = False

    @property
    def overdue(self) -> bool:
        return self.due_at is not None and self.due_at <= datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    card_ids: tuple[int, ...]
    overdue_count: int
    weak_count: int
    recent_count: int
    image_count: int


def build_cumulative_review(
    candidates: Iterable[ReviewCandidate],
    *,
    limit: int = 20,
    now: datetime | None = None,
) -> ReviewPlan:
    """Build a deterministic, interleaved review plan.

    Priority is overdue material, then weak/lapsed concepts, then recent or newly
    unlocked material.  Image cards are included when possible so review is not
    exclusively verbal.  A card appears at most once.
    """

    if limit <= 0:
        raise ValueError("review limit must be positive")
    current = now or datetime.now(UTC)
    items = list(candidates)

    overdue = sorted(
        (item for item in items if item.due_at is not None and item.due_at <= current),
        key=lambda item: (item.due_at or current, item.mastery, -item.lapses, item.card_id),
    )
    weak = sorted(
        (item for item in items if item.mastery < 0.70 or item.lapses > 0),
        key=lambda item: (item.mastery, -item.lapses, item.card_id),
    )
    recent = sorted(
        (item for item in items if item.newly_unlocked or item.last_reviewed_at is not None),
        key=lambda item: (
            not item.newly_unlocked,
            -(item.last_reviewed_at.timestamp() if item.last_reviewed_at else 0.0),
            item.card_id,
        ),
    )
    images = sorted(
        (item for item in items if item.image_card),
        key=lambda item: (item.mastery, item.card_id),
    )

    selected: list[int] = []
    selected_set: set[int] = set()
    counts = {"overdue": 0, "weak": 0, "recent": 0, "image": 0}

    def take(bucket: Sequence[ReviewCandidate], count_key: str, quota: int) -> None:
        for item in bucket:
            if len(selected) >= limit or counts[count_key] >= quota:
                break
            if item.card_id in selected_set:
                continue
            selected.append(item.card_id)
            selected_set.add(item.card_id)
            counts[count_key] += 1

    take(overdue, "overdue", limit)
    remaining = limit - len(selected)
    take(weak, "weak", max(0, (remaining * 2 + 2) // 3))
    remaining = limit - len(selected)
    take(recent, "recent", max(0, remaining))

    # Reserve visual variety when an image card has not already been selected.
    if images and not any(item.card_id in selected_set for item in images):
        replacement = images[0]
        if len(selected) < limit:
            selected.append(replacement.card_id)
        elif selected:
            selected[-1] = replacement.card_id
        selected_set.add(replacement.card_id)
        counts["image"] = 1
    else:
        counts["image"] = sum(item.card_id in selected_set for item in images)

    if len(selected) < limit:
        fallback = sorted(items, key=lambda item: (item.mastery, -item.lapses, item.card_id))
        take(fallback, "recent", limit - len(selected) + counts["recent"])

    return ReviewPlan(
        card_ids=tuple(selected[:limit]),
        overdue_count=counts["overdue"],
        weak_count=counts["weak"],
        recent_count=counts["recent"],
        image_count=counts["image"],
    )


FOUNDATION_COURSE_NAMES: tuple[str, ...] = (
    "Learning and Scientific Reasoning",
    "Matter, Measurement, and Units",
    "Atomic Structure",
    "Chemical Bonds and Reactions",
    "Water, Solutions, Acids, Bases, and Buffers",
    "Cell Structure and Membranes",
    "Biological Molecules",
    "DNA, RNA, and Protein Synthesis",
    "Enzymes, ATP, and Metabolism",
    "Cell Cycle, Mitosis, and Meiosis",
    "Genetics and Inheritance",
    "Tissues, Homeostasis, and Organ Systems",
    "Nervous and Endocrine Foundations",
    "Cardiovascular and Respiratory Foundations",
    "Digestive, Renal, and Fluid Foundations",
    "Immune and Reproductive Foundations",
    "Motion, Forces, Work, and Energy",
    "Fluids, Pressure, and Circulation Physics",
    "Electricity, Waves, Sound, and Optics",
    "Psychology Foundations",
    "Sociology Foundations",
    "Integrated Foundation Review",
)


def foundation_curriculum_skeleton() -> Curriculum:
    """Return the ordered Phase 1 course skeleton.

    Deck-level lesson content is intentionally populated course-by-course.  Each
    course initially has one installable foundation deck, allowing the storage,
    API, and UI layers to ship before thousands of cards are added.
    """

    courses: list[CurriculumCourse] = []
    previous_course: str | None = None
    previous_deck: str | None = None
    for order, name in enumerate(FOUNDATION_COURSE_NAMES):
        course_key = f"foundation-{order:02d}"
        deck_key = f"{course_key}-core"
        deck = CurriculumDeck(
            key=deck_key,
            name=f"{order:02d} {name}",
            order=0,
            prerequisite_keys=(previous_deck,) if previous_deck else (),
            checkpoint=order == len(FOUNDATION_COURSE_NAMES) - 1,
        )
        course = CurriculumCourse(
            key=course_key,
            name=name,
            order=order,
            decks=(deck,),
            prerequisite_course_keys=(previous_course,) if previous_course else (),
        )
        courses.append(course)
        previous_course = course_key
        previous_deck = deck_key
    return Curriculum(
        key="mcat-medical-foundations-phase-1",
        name="MCAT Medical Foundations — Phase 1",
        version="2.0.0",
        description=(
            "Voice-first ordered foundations with prerequisite unlocking, mastery, "
            "spaced review, and cumulative checkpoints."
        ),
        courses=tuple(courses),
    )
