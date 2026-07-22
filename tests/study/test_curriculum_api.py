from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from hermes_voice.server.study_app import create_app
from hermes_voice.study.store import StudyPaths, StudyStore


class FakeVad:
    def probability(self, frame: bytes) -> float:
        return 0.0


class FakeStt:
    async def transcribe(self, pcm: bytes) -> str:
        return ""


class FakeTts:
    async def synthesize(self, text: str) -> bytes:
        return b""


def _app(tmp_path: Path):
    root = tmp_path / "study"
    store = StudyStore(StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media"))
    return create_app(
        mode="parrot",
        vad=FakeVad(),
        stt=FakeStt(),
        tts=FakeTts(),
        study_store=store,
    )


def test_app_installs_foundation_curriculum_and_returns_ordered_courses(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        listed = client.get("/api/study/curricula")
        detail = client.get("/api/study/curricula/mcat-medical-foundations-phase-1")
        progress = client.get(
            "/api/study/curricula/mcat-medical-foundations-phase-1/progress"
        )

    assert listed.status_code == 200
    assert listed.json()["curricula"][0]["course_count"] == 22
    assert detail.status_code == 200
    courses = detail.json()["curriculum"]["courses"]
    assert courses[0]["name"] == "Learning and Scientific Reasoning"
    assert courses[-1]["name"] == "Integrated Foundation Review"
    assert progress.status_code == 200
    assert progress.json()["progress"]["next_deck"] is None


def test_bind_review_progress_continue_and_cumulative_flow(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        deck = client.post(
            "/api/study/decks",
            json={"name": "Learning Foundations", "description": "Core skills"},
        ).json()["deck"]
        cards = [
            client.post(
                f"/api/study/decks/{deck['id']}/cards",
                json={"question": f"Question {index}", "answer": f"Answer {index}"},
            ).json()["card"]
            for index in range(3)
        ]

        curriculum = client.get("/api/study/curricula/mcat-medical-foundations-phase-1").json()[
            "curriculum"
        ]
        curriculum_deck_key = curriculum["courses"][0]["decks"][0]["key"]
        bound = client.post(
            f"/api/study/curriculum-decks/{curriculum_deck_key}/bind",
            json={"deck_id": deck["id"]},
        )

        now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
        reviewed = client.post(
            f"/api/study/cards/{cards[0]['id']}/review",
            json={"rating": "again", "reviewed_at": now.isoformat()},
        )
        state = client.get(f"/api/study/cards/{cards[0]['id']}/review-state")
        due = client.get(
            "/api/study/reviews/due",
            params={"at": (now + timedelta(hours=1)).isoformat(), "limit": 10},
        )
        progress = client.get(
            "/api/study/curricula/mcat-medical-foundations-phase-1/progress"
        )
        continued = client.post(
            "/api/study/curricula/mcat-medical-foundations-phase-1/continue"
        )
        cumulative = client.post(
            "/api/study/curricula/mcat-medical-foundations-phase-1/review-session",
            json={"limit": 2},
        )

    assert bound.status_code == 200
    assert bound.json()["curriculum_deck"]["deck_id"] == deck["id"]
    assert reviewed.status_code == 200
    assert reviewed.json()["review_state"]["lapse_count"] == 1
    assert state.json()["review_state"]["rating"] == "again"
    assert due.json()["card_ids"] == [cards[0]["id"]]
    assert progress.json()["progress"]["next_deck"]["key"] == curriculum_deck_key
    assert continued.status_code == 200
    assert continued.json()["session"]["mode"] == "ordered"
    assert cumulative.status_code == 200
    assert cumulative.json()["session"]["mode"] == "cumulative"


def test_curriculum_api_returns_not_found_and_conflict_errors(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        missing_curriculum = client.get("/api/study/curricula/missing")
        missing_progress = client.get("/api/study/curricula/missing/progress")
        missing_card = client.get("/api/study/cards/9999/review-state")
        missing_bind = client.post(
            "/api/study/curriculum-decks/missing/bind", json={"deck_id": 9999}
        )
        no_lesson = client.post(
            "/api/study/curricula/mcat-medical-foundations-phase-1/continue"
        )

    assert missing_curriculum.status_code == 404
    assert missing_progress.status_code == 404
    assert missing_card.status_code == 404
    assert missing_bind.status_code == 404
    assert no_lesson.status_code == 409
