"""Speaker-verification gate.

Sits between VAD's SpeechEnded and the STT call. Embeds the captured
16 kHz int16 mono utterance with resemblyzer and accepts it only if it is
"sufficiently close" to at least one enrolled speaker. Non-enrolled audio
(other people, wind, room noise) is dropped before it ever reaches Whisper,
which both reduces spurious transcripts and keeps unwanted voices out of the
agent.

The gate is intentionally optional and fails open: if no speakers are enrolled
or the encoder cannot load, it returns ``None`` (caller treats as "accept")
so the pipeline keeps working exactly as before.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import numpy as np

logger = logging.getLogger(__name__)

# resemblyzer embeddings are unit-normalized 256-d vectors; cosine similarity
# in [-1, 1]. Empirically same-speaker ~0.95+, different-speaker ~0.45-0.6.
DEFAULT_THRESHOLD: Final[float] = 0.75
DEFAULT_STORE: Final[Path] = Path("~/.hermes-voice/speakers.json").expanduser()

_ENCODER = None
_ENCODER_LOCK = threading.Lock()


def _get_encoder() -> Any | None:
    """Lazily load the VoiceEncoder (CPU). Returns None if unavailable."""
    global _ENCODER
    if _ENCODER is not None or getattr(_ENCODER, "_failed", False):
        return _ENCODER
    with _ENCODER_LOCK:
        if _ENCODER is not None:
            return _ENCODER
        try:
            from resemblyzer import VoiceEncoder

            _ENCODER = VoiceEncoder()
            logger.info("speaker_gate: VoiceEncoder loaded (CPU)")
        except Exception:  # pragma: no cover - environment dependent
            logger.exception("speaker_gate: failed to load VoiceEncoder")
            _ENCODER = type("_Failed", (), {"_failed": True})()
        return _ENCODER if not getattr(_ENCODER, "_failed", False) else None


@dataclass
class SpeakerGateConfig:
    """Config for the speaker gate.

    enabled   - master switch
    threshold - cosine-similarity cutoff for "is this an enrolled speaker"
    store     - path to the JSON file holding enrolled embeddings
    """

    enabled: bool = False
    threshold: float = DEFAULT_THRESHOLD
    store: Path = field(default_factory=lambda: DEFAULT_STORE)

    @classmethod
    def from_section(cls, section: dict[str, Any] | None) -> SpeakerGateConfig:
        if not section:
            return cls()
        return cls(
            enabled=bool(section.get("enabled", False)),
            threshold=float(section.get("threshold", DEFAULT_THRESHOLD)),
            store=Path(section.get("store", DEFAULT_STORE)).expanduser(),
        )


class SpeakerGate:
    """Verify that an utterance belongs to an enrolled speaker."""

    def __init__(self, config: SpeakerGateConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._speakers: dict[str, list[np.ndarray]] = {}
        if config.enabled:
            self._load()

    # --- enrollment -----------------------------------------------------
    def enroll(self, name: str, embedding: np.ndarray) -> None:
        with self._lock:
            self._speakers.setdefault(name, []).append(embedding.astype(np.float32))
        self._save()

    @property
    def enrolled_names(self) -> list[str]:
        with self._lock:
            return sorted(self._speakers)

    @property
    def is_configured(self) -> bool:
        return self._config.enabled and bool(self.enrolled_names)

    # --- verification ---------------------------------------------------
    def verify(self, embedding: np.ndarray) -> tuple[bool, float, str | None]:
        """Return (accepted, best_score, best_speaker).

        If the gate is disabled or has no enrolled speakers, returns
        (True, 1.0, None) so callers fail open.
        """
        if not self._config.enabled:
            return True, 1.0, None
        with self._lock:
            if not self._speakers:
                return True, 1.0, None
            best_score = -1.0
            best_speaker: str | None = None
            for name, embs in self._speakers.items():
                for e in embs:
                    s = float(np.dot(embedding, e))
                    if s > best_score:
                        best_score = s
                        best_speaker = name
        accepted = best_score >= self._config.threshold
        return accepted, best_score, best_speaker

    # --- embedding ------------------------------------------------------
    @staticmethod
    def embed(pcm_16k_int16: bytes) -> np.ndarray | None:
        """Embed raw 16 kHz int16 mono PCM. Returns None on failure."""
        enc = _get_encoder()
        if enc is None:
            return None
        try:
            audio = np.frombuffer(pcm_16k_int16, dtype=np.int16).astype(np.float32) / 32768.0
            if audio.size < 8000:  # < 0.5s: too short to embed reliably
                return np.zeros(256, dtype=np.float32)
            from resemblyzer import preprocess_wav

            wav = preprocess_wav(audio, source_sr=16000)
            return np.asarray(enc.embed_utterance(wav), dtype=np.float32)
        except Exception:  # pragma: no cover - defensive
            logger.exception("speaker_gate: embed failed")
            return None

    # --- persistence ----------------------------------------------------
    def _load(self) -> None:
        path = self._config.store
        if not path.exists():
            logger.info("speaker_gate: no store at %s (starting empty)", path)
            return
        try:
            data = json.loads(path.read_text())
            with self._lock:
                self._speakers = {
                    name: [np.asarray(v, dtype=np.float32) for v in vecs]
                    for name, vecs in data.get("speakers", {}).items()
                }
            logger.info(
                "speaker_gate: loaded %d speaker(s) from %s",
                len(self._speakers),
                path,
            )
        except Exception:
            logger.exception("speaker_gate: failed to load store")

    def _save(self) -> None:
        path = self._config.store
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                "threshold": self._config.threshold,
                "speakers": {
                    name: [e.tolist() for e in embs] for name, embs in self._speakers.items()
                },
            }
        path.write_text(json.dumps(data, indent=2))
        logger.info("speaker_gate: saved %d speaker(s) to %s", len(self._speakers), path)
