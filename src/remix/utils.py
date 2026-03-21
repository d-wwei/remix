from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


WORD_RE = re.compile(r"[A-Za-z0-9_./:-]+")


def slugify(value: str, *, separator: str = "-") -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", separator, value.strip().lower())
    normalized = re.sub(rf"{re.escape(separator)}+", separator, normalized)
    return normalized.strip(separator) or "artifact"


def skillify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized)
    normalized = normalized.strip(".-") or "remix"
    if normalized[0].isdigit():
        normalized = f"skill-{normalized}"
    return normalized


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def top_words(text: str, *, limit: int = 25) -> List[str]:
    frequencies: Dict[str, int] = {}
    for token in WORD_RE.findall(text.lower()):
        if len(token) < 3 or token.isdigit():
            continue
        frequencies[token] = frequencies.get(token, 0) + 1
    ranked = sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _count in ranked[:limit]]


def keyword_overlap(left: Iterable[str], right: Iterable[str]) -> int:
    return len(set(left) & set(right))


def limited(items: Sequence[Any], *, limit: int) -> List[Any]:
    return list(items[:limit])


def compact_excerpt(text: str, *, max_chars: int = 300) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def markdown_bullets(items: Sequence[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def dump_json_text(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def infer_license_name(text: str) -> str:
    lowered = text.lower()
    if "apache license" in lowered or "apache-2.0" in lowered:
        return "Apache-2.0"
    if "mit license" in lowered or "mit" == lowered.strip():
        return "MIT"
    if "bsd" in lowered:
        return "BSD"
    if "mozilla public license" in lowered or "mpl-2.0" in lowered:
        return "MPL-2.0"
    if "gnu general public license" in lowered or "gpl" in lowered:
        return "GPL"
    if "creative commons" in lowered:
        return "CC"
    return "unknown"
