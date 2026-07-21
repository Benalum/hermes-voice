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
    store = StudyStore(
        StudyPaths(root=root, database=root / "study.sqlite3", media=root / "media")
    )
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
        detail = client.get(
            "/api/study/curricula/mcat-medical-foundations-phase-1"
        )

    assert listed.status_code == 200
    assert listed.json()["curricula"][0]["course_count"] == 22
    assert detail.status_code == 200
    courses = detail.json()["curriculum"]["courses"]
    assert courses[0]["name"] == "Learning and Scientific Reasoning"
    assert courses[-1]["name"] == "Integrated Foundation Review"


def test_bind_review_and_due_flow(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        deck = client.post(
            "/api/study/decks",
            json={"name": "Learning Foundations", "description": "Core skills"},
        ).json()["deck"]
        card = client.post(
            f"/api/study/decks/{deck['id']}/cards",
            json={"question": "What is active recall?", "answer": "Retrieving from memory."},
        ).json()["card"]

        curriculum = client.get(
            "/api/study/curricula/mcat-medical-foundations-phase-1"
        ).json()["curriculum"]
        curriculum_deck_key = curriculum["courses"][0]["decks"][0]["key"]
        bound = client.post(
            f"/api/study/curriculum-decks/{curriculum_deck_key}/bind",
            json={"deck_id": deck["id"]},
        )

        now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
        reviewed = client.post(
            f"/api/study/cards/{card['id']}/review",
            json={"rating": "again", "reviewed_at": now.isoformat()},
        )
        state = client.get(f"/api/study/cards/{card['id']}/review-state")
        due = client.get(
            "/api/study/reviews/due",
            params={"at": (now + timedelta(hours=1)).isoformat(), "limit": 10},
        )

    assert bound.status_code == 200
    assert bound.json()["curriculum_deck"]["deck_id"] == deck["id"]
    assert reviewed.status_code == 200
    assert reviewed.json()["review_state"]["lapse_count"] == 1
    assert state.json()["review_state"]["rating"] == "again"
    assert due.json()["card_ids"] == [card["id"]]


def test_curriculum_api_returns_not_found_errors(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        missing_curriculum = client.get("/api/study/curricula/missing")
        missing_card = client.get("/api/study/cards/9999/review-state")
        missing_bind = client.post(
            "/api/study/curriculum-decks/missing/bind", json={"deck_id": 9999}
        )

    assert missing_curriculum.status_code == 404
    assert missing_card.status_code == 404
    assert missing_bind.status_code == 404
