from __future__ import annotations

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


def make_store(tmp_path: Path) -> StudyStore:
    root = tmp_path / "study"
    return StudyStore(
        StudyPaths(
            root=root,
            database=root / "study.sqlite3",
            media=root / "media",
        )
    )


def test_study_app_preserves_health_and_adds_study_routes(tmp_path: Path) -> None:
    app = create_app(
        mode="parrot",
        vad=FakeVad(),
        stt=FakeStt(),
        tts=FakeTts(),
        study_store=make_store(tmp_path),
    )

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        voice_page = client.get("/")
        assert voice_page.status_code == 200
        assert 'href="/study"' in voice_page.text
        assert 'id="study-live"' in voice_page.text

        study_page = client.get("/study")
        assert study_page.status_code == 200
        assert "Hermes Study" in study_page.text

        decks = client.get("/api/study/decks")
        assert decks.status_code == 200
        assert decks.json() == {"decks": []}
