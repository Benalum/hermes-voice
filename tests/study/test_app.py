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


def test_phase1_reference_media_is_served_inline(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path)) as client:
        installed = client.post("/api/study/content-packs/mcat-phase-1-v1")
        assert installed.status_code == 200
        result = installed.json()["result"]
        assert result["courses"] == 22
        assert result["total_cards"] == 660
        assert result["bindings"] == 22

        decks = client.get("/api/study/decks").json()["decks"]
        assert len(decks) == 22
        first_deck = next(
            deck
            for deck in decks
            if deck["name"] == "00 Learning and Scientific Reasoning"
        )
        cards = client.get(f"/api/study/decks/{first_deck['id']}/cards").json()["cards"]
        visual_card = next(
            card
            for card in cards
            if card["media"]["question"]
            or card["media"]["answer"]
            or card["media"]["notes"]
        )
        media = (
            visual_card["media"]["question"]
            or visual_card["media"]["answer"]
            or visual_card["media"]["notes"]
        )[0]

        image = client.get(media["url"])
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/png")
        assert image.headers["content-disposition"].startswith("inline;")
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
