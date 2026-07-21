"""HTTP endpoint for installing the versioned Phase 1 Study content pack."""

from __future__ import annotations

from fastapi import APIRouter

from hermes_voice.study.curriculum_store import CurriculumStore
from hermes_voice.study.phase1_content import PACK_KEY, install_phase1_content
from hermes_voice.study.store import StudyStore


def create_pack_router(store: StudyStore, curriculum_store: CurriculumStore) -> APIRouter:
    router = APIRouter(prefix="/api/study/content-packs", tags=["study"])

    @router.post(f"/{PACK_KEY}")
    def install_pack() -> dict[str, object]:
        result = install_phase1_content(store, curriculum_store)
        return {
            "pack": PACK_KEY,
            "result": result,
            "decks": store.list_decks(),
            "curricula": curriculum_store.list_curricula(),
        }

    return router
