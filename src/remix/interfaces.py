from __future__ import annotations

from typing import Any, Dict, List, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Validator(Protocol):
    """Validates generated artifacts (e.g. skill manifests, governor proposals)."""

    def validate_manifest(self, manifest: Dict[str, Any]) -> None: ...

    def validate_proposal(self, proposal: Dict[str, Any]) -> None: ...


@runtime_checkable
class EvolutionBackend(Protocol):
    """Optional backend for self-evolution and governance integration."""

    def detect_governor(self) -> bool: ...

    def record_experience(
        self,
        *,
        kind: str,
        summary: str,
        source_origin: str,
        outcome: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> None: ...


@runtime_checkable
class Analyzer(Protocol):
    """Pluggable analysis backend.

    The default implementation uses heuristic scoring (see planning.SourceAnalyzer).
    Replace with an LLM-backed implementation for deeper semantic analysis.

    Each analyze call receives one normalized source and should return an analysis
    report dict with at least: source_id, scores (dict[str, float 0-5]),
    strengths (list[str]), weaknesses (list[str]).
    """

    def analyze_source(
        self,
        source: Dict[str, Any],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> Dict[str, Any]: ...

    def analyze_sources(
        self,
        normalized_sources: Sequence[Dict[str, Any]],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]: ...
