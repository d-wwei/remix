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


@runtime_checkable
class ContentSynthesizer(Protocol):
    """Pluggable content synthesis backend for the build phase.

    The default implementation (HeuristicContentSynthesizer in builder.py) uses
    structural analysis to produce rich content outlines from source units.
    Replace with an LLM-backed implementation for true content fusion.

    The synthesizer receives all analysis data and the selected strategy, and
    produces two outputs:
    - A structured content outline (merged sections with source-tagged content)
    - A synthesis guide (instructions for the operator to complete the fusion)
    """

    def generate_content_outline(
        self,
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        normalized_sources: Sequence[Dict[str, Any]],
        analysis_reports: Sequence[Dict[str, Any]],
    ) -> str:
        """Return a Markdown content outline with merged sections, source-tagged
        bullet points, conflict markers, and adaptation notes."""
        ...

    def generate_synthesis_guide(
        self,
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        normalized_sources: Sequence[Dict[str, Any]],
        analysis_reports: Sequence[Dict[str, Any]],
        comparison: Dict[str, Any],
    ) -> str:
        """Return a Markdown synthesis guide with explicit instructions for
        completing the content fusion."""
        ...
