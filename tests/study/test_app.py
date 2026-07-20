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


def make_app(tmp_path: Path):
    return create_app(
        mode="parrot",
        vad=FakeVad(),
        stt=FakeStt(),
        tts=FakeTts(),
        study_store=make_store(tmp_path),
    )


def test_study_app_preserves_health_and_adds_study_routes(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        voice_page = client.get("/")
        assert voice_page.status_code == 200
        assert 'href="/study"' in voice_page.text
        assert 'id="study-live"' not in voice_page.text
        assert "/static/study-live.mjs" not in voice_page.text

        study_page = client.get("/study")
        assert study_page.status_code == 200
        assert "Hermes Study" in study_page.text

        decks = client.get("/api/study/decks")
        assert decks.status_code == 200
        assert decks.json() == {"decks": []}


def test_mcat_reference_media_is_served_inline(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        installed = client.post("/api/study/starter-packs/mcat-foundations")
        assert installed.status_code == 200

        decks = client.get("/api/study/decks").json()["decks"]
        biology = next(
            deck
            for deck in decks
            if deck["name"] == "MCAT Biology: Cells, Genetics & Organ Systems"
        )
        cards = client.get(f"/api/study/decks/{biology['id']}/cards").json()["cards"]
        transport = next(
            card
            for card in cards
            if card["question"].startswith("How do simple diffusion")
        )
        media_url = transport["media"]["question"][0]["url"]

        image = client.get(media_url)
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/svg+xml")
        assert image.headers["content-disposition"].startswith("inline;")
        assert image.content.startswith(b"<svg")
