# Hermes Curriculum Engine v2

Hermes Study v2 turns the existing local deck/card system into a reusable,
voice-first curriculum engine.  Existing user-created decks remain compatible
and immediately available.  Progression rules apply only to decks explicitly
installed as part of a curriculum.

## Product goals

- teach concepts conversationally before testing recall;
- store question, answer, notes, and local media together;
- unlock foundations in prerequisite order;
- track mastery at card, deck, course, and concept levels;
- schedule older material with spaced repetition;
- generate cumulative reviews without duplicating cards;
- support MCAT first while keeping the engine curriculum-neutral.

## Phase 1 curriculum

`MCAT Medical Foundations — Phase 1` contains 22 ordered courses:

1. Learning and Scientific Reasoning
2. Matter, Measurement, and Units
3. Atomic Structure
4. Chemical Bonds and Reactions
5. Water, Solutions, Acids, Bases, and Buffers
6. Cell Structure and Membranes
7. Biological Molecules
8. DNA, RNA, and Protein Synthesis
9. Enzymes, ATP, and Metabolism
10. Cell Cycle, Mitosis, and Meiosis
11. Genetics and Inheritance
12. Tissues, Homeostasis, and Organ Systems
13. Nervous and Endocrine Foundations
14. Cardiovascular and Respiratory Foundations
15. Digestive, Renal, and Fluid Foundations
16. Immune and Reproductive Foundations
17. Motion, Forces, Work, and Energy
18. Fluids, Pressure, and Circulation Physics
19. Electricity, Waves, Sound, and Optics
20. Psychology Foundations
21. Sociology Foundations
22. Integrated Foundation Review

## Delivery milestones

### V2.1 — Policy engine

- curriculum/course/deck definitions;
- prerequisite validation;
- conservative mastery calculation;
- deck and course unlock decisions with learner-facing reasons;
- deterministic cumulative review selection.

### V2.2 — SQLite migration and API

Add backward-compatible tables for:

- curricula and courses;
- curriculum deck membership and ordering;
- deck prerequisites;
- per-card scheduling state;
- concepts and card-concept links;
- learner concept mastery.

Add API resources for curriculum progress, unlocked decks, due reviews, and
cumulative session creation.

### V2.3 — Spaced repetition

Support `again`, `hard`, `good`, `easy`, and `skipped`.  Existing voice outcomes
map as follows:

- wrong → again
- almost → hard
- correct → good
- easy → easy
- skip → skipped

Persist due date, stability, difficulty, review count, lapse count, and last
rating per card.  Review sessions update the original card record; review decks
never duplicate cards.

### V2.4 — Voice-first lessons

Each curriculum card may include:

- a teaching introduction;
- a spoken prompt distinct from the visible question;
- accepted concepts;
- common misconceptions and corrections;
- prerequisite concepts;
- a follow-up retrieval prompt;
- question, answer, and notes media.

Hermes teaches briefly, requests a learner explanation, evaluates the concepts
present, corrects one misconception at a time, and lets the learner retain final
control of the review rating.

### V2.5 — Browser progression UI

Show:

- ordered courses and decks;
- locked/unlocked/completed states;
- unlock requirements;
- due and overdue counts;
- course and concept mastery;
- Today's Review and cumulative checkpoints.

### V2.6 — Complete foundations content

Build and validate all Phase 1 lessons, cards, notes, explanations, and original
media course-by-course.  Content installation remains idempotent and versioned.
Automated validation checks identifiers, prerequisites, duplicate questions,
media links, learning objectives, and expected concept coverage.

## Compatibility rules

1. Existing decks and cards must continue to load without migration input.
2. User-created decks are not locked by curriculum progression.
3. Starter-pack installation remains idempotent.
4. Card media stays local and is not uploaded to Telegram.
5. Review sessions reference original cards.
6. Schema migrations must be safe to rerun.
7. CT102 and CT103 retain isolated Study databases and learner progress.
