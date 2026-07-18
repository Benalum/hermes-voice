"""Unit tests for the speaker-verification gate (no model downloads)."""

import numpy as np

from hermes_voice.kit.speaker_gate import SpeakerGate, SpeakerGateConfig


def _vec(*vals: float) -> np.ndarray:
    base = np.zeros(256, dtype=np.float32)
    for i, v in enumerate(vals):
        base[i] = v
    return base / np.linalg.norm(base)


def test_disabled_gate_accepts_everything() -> None:
    gate = SpeakerGate(SpeakerGateConfig(enabled=False))
    assert gate.verify(_vec(1.0))[0] is True


def test_no_enrolled_speakers_accepts(tmp_path) -> None:
    cfg = SpeakerGateConfig(enabled=True, store=tmp_path / "sp.json")
    gate = SpeakerGate(cfg)
    assert gate.is_configured is False
    # fails open when nothing enrolled
    assert gate.verify(_vec(1.0))[0] is True


def test_enroll_then_verify_same_speaker_accepted(tmp_path) -> None:
    cfg = SpeakerGateConfig(enabled=True, threshold=0.75, store=tmp_path / "sp.json")
    gate = SpeakerGate(cfg)
    gate.enroll("alex", _vec(1.0, 0.2, 0.1))
    accepted, score, speaker = gate.verify(_vec(0.98, 0.22, 0.09))
    assert accepted is True
    assert speaker == "alex"
    assert score >= 0.75


def test_verify_different_speaker_rejected(tmp_path) -> None:
    cfg = SpeakerGateConfig(enabled=True, threshold=0.75, store=tmp_path / "sp.json")
    gate = SpeakerGate(cfg)
    gate.enroll("alex", _vec(1.0, 0.0, 0.0))
    gate.enroll("partner", _vec(0.0, 1.0, 0.0))
    # a speaker orthogonal to both enrolled vectors
    accepted, score, _speaker = gate.verify(_vec(0.0, 0.0, 1.0))
    assert accepted is False
    assert score < 0.75


def test_enrollment_persists_to_disk(tmp_path) -> None:
    store = tmp_path / "sp.json"
    cfg = SpeakerGateConfig(enabled=True, store=store)
    gate = SpeakerGate(cfg)
    gate.enroll("alex", _vec(1.0))
    assert store.exists()

    # reload from disk
    gate2 = SpeakerGate(cfg)
    assert "alex" in gate2.enrolled_names
    accepted, _, _ = gate2.verify(_vec(1.0))
    assert accepted is True
