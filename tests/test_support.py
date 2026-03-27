from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Optional: skill-se-kit paths for integration tests
SKILL_SE_KIT_SRC = ROOT.parent / "skill-se-kit" / "src"
PROTOCOL_ROOT = ROOT.parent / "skill-evolution-protocol"
SKILL_SE_KIT_EXAMPLES = ROOT.parent / "skill-se-kit" / "examples"

if SKILL_SE_KIT_SRC.exists() and str(SKILL_SE_KIT_SRC) not in sys.path:
    sys.path.insert(0, str(SKILL_SE_KIT_SRC))


def load_example_manifest(name: str = "standalone.manifest.json"):
    with (SKILL_SE_KIT_EXAMPLES / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def has_skill_se_kit() -> bool:
    try:
        import skill_se_kit  # noqa: F401
        return True
    except ImportError:
        return False
