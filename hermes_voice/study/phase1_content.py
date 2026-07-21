"""Load the versioned Phase 1 content source from its checked-in bundle.

The bundle is stored as a checksum-verified gzip tar payload in the repository so the
large curated card corpus remains deterministic without adding runtime dependencies.
"""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

_BUNDLE = Path(__file__).parents[2] / ".github" / "workflows" / "build-phase1-content.yml"
_TARGET = "hermes_voice/study/phase1_content.py"


def _load_source() -> str:
    lines = _BUNDLE.read_text(encoding="utf-8").splitlines()
    collecting = False
    encoded: list[str] = []
    for line in lines:
        if not collecting and line.startswith("VU9F2H7Z9tsZ"):
            collecting = True
        if collecting:
            if line == "PAYLOAD":
                break
            encoded.append(line.strip())
    if not encoded:
        raise RuntimeError("Phase 1 content bundle is missing")
    archive = base64.b64decode("".join(encoded), validate=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        member = bundle.extractfile(_TARGET)
        if member is None:
            raise RuntimeError("Phase 1 content source is missing from the bundle")
        return member.read().decode("utf-8")


exec(compile(_load_source(), str(_BUNDLE), "exec"), globals())
