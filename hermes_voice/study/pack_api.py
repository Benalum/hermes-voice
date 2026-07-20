"""HTTP endpoints for installing curated Study starter packs."""

from __future__ import annotations

from fastapi import APIRouter

from hermes_voice.study.starter_packs import install_mcat_foundations
from hermes_voice.study.store import StudyStore


def create_pack_router(store: StudyStore) -> APIRouter:
    router = APIRouter(prefix="/api/study/starter-packs", tags=["study"])

    @router.post("/mcat-foundations")
    def install_pack() -> dict[str, object]:
        return {
            "pack": "mcat-foundations",
            "result": install_mcat_foundations(store),
            "decks": store.list_decks(),
        }

    return router
