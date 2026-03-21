from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SKILL_SE_KIT_SRC = ROOT.parent / "skill-se-kit" / "src"

for path in (SRC, SKILL_SE_KIT_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

PROTOCOL_ROOT = ROOT.parent / "skill-evolution-protocol"
SKILL_SE_KIT_EXAMPLES = ROOT.parent / "skill-se-kit" / "examples"


def load_example_manifest(name: str = "standalone.manifest.json"):
    with (SKILL_SE_KIT_EXAMPLES / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)
