"""Load the versioned Phase 1 content source from its checked-in bundle."""

from __future__ import annotations

import base64
import hashlib
import io
import tarfile
from pathlib import Path

_BUNDLE = Path(__file__).with_name("phase1_content.bundle")
_TARGET = "hermes_voice/study/phase1_content.py"
_ARCHIVE_SHA256 = "e4a9c7f8bb44dfdb73de3373ef225f8badda7706b4e59d9a2290fdcb7d0e5051"


def _load_source() -> str:
    lines = _BUNDLE.read_text(encoding="utf-8").splitlines()
    collecting = False
    encoded: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not collecting and stripped.startswith("VU9F2H7Z9tsZ"):
            collecting = True
        if not collecting:
            continue
        if stripped == "PAYLOAD":
            break
        encoded.append(stripped)

    if not encoded:
        raise RuntimeError("Phase 1 content bundle is missing")

    archive = base64.b64decode("".join(encoded), validate=True)
    digest = hashlib.sha256(archive).hexdigest()
    if digest != _ARCHIVE_SHA256:
        raise RuntimeError("Phase 1 content bundle checksum does not match")

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        member = bundle.extractfile(_TARGET)
        if member is None:
            raise RuntimeError("Phase 1 content source is missing from the bundle")
        return member.read().decode("utf-8")


exec(compile(_load_source(), str(_BUNDLE), "exec"), globals())
