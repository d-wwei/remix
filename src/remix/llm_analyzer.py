"""LLM-powered analyzer plugin for Remix.

This module provides an LLMAnalyzer that implements the Analyzer protocol
from interfaces.py, and an LLMContentSynthesizer that implements the
ContentSynthesizer protocol. Both are designed to be drop-in replacements
for the default heuristic implementations.

Usage:
    # Via CLI:
    #   remix run --brief brief.json --sources sources.json --analyzer llm
    #
    # Via Python:
    #   from remix.llm_analyzer import LLMAnalyzer, LLMContentSynthesizer
    #   runtime = RemixRuntime(analyzer=LLMAnalyzer(api_key="sk-..."))

TODO: Connect to an actual LLM API. The current implementation raises
NotImplementedError with clear guidance on what to implement.

To integrate with the Anthropic Claude API:
    1. pip install anthropic
    2. Set ANTHROPIC_API_KEY in your environment, or pass api_key to the constructor
    3. Implement _call_llm() to send prompts and parse structured responses
    4. The prompts are already constructed; you only need the API transport layer

To integrate with other LLM providers:
    - Implement _call_llm() with your provider's SDK
    - Ensure the response is parsed into the expected dict structure
    - The prompt construction methods can be reused as-is
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence

from remix.utils import compact_excerpt, limited, top_words


class LLMAnalyzer:
    """Analyzer implementation that uses an LLM for semantic source analysis.

    Implements the Analyzer protocol from interfaces.py. When connected to a
    real LLM API, this produces much richer analysis than the heuristic
    SourceAnalyzer, including:
    - Semantic understanding of source purpose and design intent
    - Cross-source thematic extraction and conflict detection
    - Nuanced quality scoring based on content understanding
    - Richer reusable pattern identification

    Constructor Args:
        api_key: API key for the LLM provider. If None, reads from
            ANTHROPIC_API_KEY environment variable.
        model: Model identifier (default: "claude-sonnet-4-20250514").
        max_tokens: Maximum tokens per LLM call (default: 4096).
        temperature: Sampling temperature (default: 0.2 for consistency).

    Example:
        >>> analyzer = LLMAnalyzer(api_key="sk-ant-...")
        >>> runtime = RemixRuntime(analyzer=analyzer)
        >>> summary = runtime.run(brief=brief, sources=sources)
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def analyze_sources(
        self,
        normalized_sources: Sequence[Dict[str, Any]],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Analyze all sources, potentially in parallel.

        For LLM-backed analysis, this sends one prompt per source.
        Each prompt includes the brief context so the LLM can assess
        relevance and fitness.
        """
        workers = min(4, max(1, len(normalized_sources)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    self.analyze_source,
                    source,
                    brief=brief,
                    target_profile=target_profile,
                )
                for source in normalized_sources
            ]
            return [future.result() for future in futures]

    def analyze_source(
        self,
        source: Dict[str, Any],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze a single source using LLM semantic understanding.

        The LLM receives:
        - The source content summary and extracted units
        - The brief (target job, constraints, success criteria)
        - The target profile requirements

        It returns a structured analysis with scores, strengths,
        weaknesses, reusable patterns, and failure modes.
        """
        prompt = self._build_analysis_prompt(source, brief=brief, target_profile=target_profile)
        response = self._call_llm(prompt)
        return self._parse_analysis_response(response, source=source, brief=brief)

    def _build_analysis_prompt(
        self,
        source: Dict[str, Any],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> str:
        """Construct the analysis prompt for a single source.

        This prompt is designed to extract structured analysis that maps
        directly to the analysis report schema expected by the comparison
        engine and strategy synthesizer.
        """
        units_text = "\n".join(
            f"  - [{u['kind']}] {u['name']}: {u.get('summary', 'no summary')}"
            for u in source.get("units", [])[:12]
        )
        return f"""You are an expert artifact analyst for a software reconstruction tool.

Analyze this source material for its fitness and reusability in building a new artifact.

## Brief (what we're building)
- Target job: {brief.get('target_job', 'unspecified')}
- Target profile: {target_profile['profile_id']}
- Success criteria: {', '.join(brief.get('success_criteria', ['none specified']))}
- Constraints: {', '.join(brief.get('constraints', ['none']))}

## Source to analyze
- Source ID: {source['source_id']}
- Kind: {source['source_kind']}
- Artifact types detected: {', '.join(source.get('artifact_types', ['generic']))}
- Keywords: {', '.join(source.get('keywords', [])[:15])}
- Content summary: {source.get('content_summary', 'no summary')}

## Extracted units
{units_text}

## Your task
Return a JSON object with these fields:
{{
  "scores": {{
    "task_fit": <0-5 float>,
    "objective_coverage": <0-5>,
    "extensibility": <0-5>,
    "structural_clarity": <0-5>,
    "maintainability": <0-5>
  }},
  "strengths": ["strength 1", "strength 2", ...],
  "weaknesses": ["weakness 1", ...],
  "reusable_patterns": [
    {{"unit_id": "...", "name": "...", "kind": "...", "why_reusable": "..."}}
  ],
  "failure_modes": ["risk 1", ...],
  "semantic_themes": ["theme 1", "theme 2", ...],
  "adaptation_notes": "Free-text notes on how to adapt this source for the target."
}}

Be specific and grounded in the actual content. Score conservatively.
Return ONLY the JSON object, no markdown fencing."""

    def _call_llm(self, prompt: str) -> str:
        """Send a prompt to the LLM and return the raw response text.

        TODO: Implement this method to connect to your LLM provider.

        For Anthropic Claude API:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text

        For OpenAI-compatible APIs:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        """
        raise NotImplementedError(
            "LLMAnalyzer._call_llm() is not yet connected to an LLM API. "
            "See the docstring and module-level TODO for integration instructions. "
            "Install 'anthropic' and set ANTHROPIC_API_KEY, then implement this method."
        )

    def _parse_analysis_response(
        self,
        response: str,
        *,
        source: Dict[str, Any],
        brief: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse the LLM response into a standard analysis report dict.

        Falls back to a minimal valid report if parsing fails.
        """
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            # Attempt to extract JSON from markdown fencing
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
            else:
                return self._fallback_report(source, brief=brief)

        scores = parsed.get("scores", {})
        reusable_patterns = [
            {
                "unit_id": p.get("unit_id", f"{source['source_id']}:llm:{i}"),
                "name": p.get("name", "unnamed"),
                "kind": p.get("kind", "pattern"),
            }
            for i, p in enumerate(parsed.get("reusable_patterns", []))
        ]
        return {
            "source_id": source["source_id"],
            "target_capability": brief.get("target_job", "unspecified"),
            "scope": compact_excerpt(source.get("content_summary", ""), max_chars=160),
            "core_structure": source.get("file_tree_summary", [])[:12],
            "workflow": [u["name"] for u in source.get("units", [])[:4]] or ["implicit workflow"],
            "interfaces": source.get("entrypoints", []),
            "strengths": parsed.get("strengths", ["LLM analysis completed."]),
            "weaknesses": parsed.get("weaknesses", []),
            "performance_strengths": parsed.get("strengths", [])[:2],
            "failure_modes": parsed.get("failure_modes", []),
            "maintainability_notes": [parsed.get("adaptation_notes", "See LLM analysis.")],
            "portability_notes": [],
            "test_maturity": "high" if source.get("tests_presence") else "low",
            "reusable_patterns": reusable_patterns,
            "non_reusable_or_risky_elements": [],
            "provenance_implications": [f"License: {source.get('license', 'unknown')}."],
            "scores": {
                "task_fit": scores.get("task_fit", 2.5),
                "objective_coverage": scores.get("objective_coverage", 2.5),
                "extensibility": scores.get("extensibility", 2.5),
                "api_coherence": scores.get("api_coherence", 2.5),
                "structural_clarity": scores.get("structural_clarity", 2.5),
                "maintainability": scores.get("maintainability", 2.5),
                "operator_experience": scores.get("operator_experience", 2.5),
                "compatibility_risk": scores.get("compatibility_risk", 2.5),
                "integration_fit": scores.get("integration_fit", 2.5),
                "testability": scores.get("testability", 2.5),
                "maintenance_cost": scores.get("maintenance_cost", 2.5),
                "provenance_safety": scores.get("provenance_safety", 2.5),
                "dependency_safety": scores.get("dependency_safety", 2.5),
                "dependency_realism": scores.get("dependency_realism", 2.5),
            },
            "keywords": list(source.get("keywords", []))[:20],
            # LLM-enriched extras
            "semantic_themes": parsed.get("semantic_themes", []),
            "adaptation_notes": parsed.get("adaptation_notes", ""),
        }

    def _fallback_report(self, source: Dict[str, Any], *, brief: Dict[str, Any]) -> Dict[str, Any]:
        """Produce a minimal valid report when LLM response parsing fails."""
        return {
            "source_id": source["source_id"],
            "target_capability": brief.get("target_job", "unspecified"),
            "scope": compact_excerpt(source.get("content_summary", ""), max_chars=160),
            "core_structure": source.get("file_tree_summary", [])[:12],
            "workflow": ["implicit workflow"],
            "interfaces": source.get("entrypoints", []),
            "strengths": ["Source provides reusable material."],
            "weaknesses": ["LLM analysis could not be completed."],
            "performance_strengths": [],
            "failure_modes": ["LLM analysis fallback was used."],
            "maintainability_notes": [],
            "portability_notes": [],
            "test_maturity": "low",
            "reusable_patterns": [],
            "non_reusable_or_risky_elements": [],
            "provenance_implications": [f"License: {source.get('license', 'unknown')}."],
            "scores": {dim: 2.5 for dim in [
                "task_fit", "objective_coverage", "extensibility", "api_coherence",
                "structural_clarity", "maintainability", "operator_experience",
                "compatibility_risk", "integration_fit", "testability",
                "maintenance_cost", "provenance_safety", "dependency_safety",
                "dependency_realism",
            ]},
            "keywords": list(source.get("keywords", []))[:20],
        }


class LLMContentSynthesizer:
    """ContentSynthesizer implementation that uses an LLM for true content fusion.

    Implements the ContentSynthesizer protocol from interfaces.py. When connected
    to a real LLM API, this produces fully synthesized content rather than
    structured outlines.

    TODO: Implement _call_llm() -- see LLMAnalyzer._call_llm() for guidance.
    The prompt construction is already done; you only need the API call.

    Constructor Args:
        api_key: API key for the LLM provider.
        model: Model identifier (default: "claude-sonnet-4-20250514").
        max_tokens: Maximum tokens per LLM call (default: 8192 for synthesis).
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8192,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens

    def generate_content_outline(
        self,
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        normalized_sources: Sequence[Dict[str, Any]],
        analysis_reports: Sequence[Dict[str, Any]],
    ) -> str:
        """Use an LLM to produce a fully fused content document.

        Unlike the heuristic version which produces an outline with source
        tags, this version asks the LLM to actually synthesize the content
        into a coherent document.
        """
        prompt = self._build_outline_prompt(
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
            normalized_sources=normalized_sources,
            analysis_reports=analysis_reports,
        )
        return self._call_llm(prompt)

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
        """Use an LLM to produce a synthesis guide.

        With LLM synthesis, the guide focuses on what was done and
        what the operator should review, rather than what they need to write.
        """
        prompt = self._build_guide_prompt(
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
            comparison=comparison,
        )
        return self._call_llm(prompt)

    def _build_outline_prompt(self, **kwargs) -> str:
        brief = kwargs["brief"]
        target_profile = kwargs["target_profile"]
        strategy = kwargs["selected_strategy"]
        sources = kwargs["normalized_sources"]

        source_summaries = "\n".join(
            f"### {s['source_id']}\n{s.get('content_summary', 'no summary')}"
            for s in sources
        )
        return f"""Synthesize a complete {target_profile['profile_id']} artifact document.

## Brief
- Name: {brief.get('name', 'Unnamed')}
- Target job: {brief.get('target_job', 'unspecified')}
- Success criteria: {', '.join(brief.get('success_criteria', []))}

## Strategy: {strategy['name']}
- Preserve: {', '.join(strategy.get('preserve', []))}
- Adapt: {', '.join(strategy.get('adapt', []))}
- Discard: {', '.join(strategy.get('discard', []))}

## Source Materials
{source_summaries}

Write a complete, coherent Markdown document that synthesizes these sources
according to the strategy. Do not use placeholder text."""

    def _build_guide_prompt(self, **kwargs) -> str:
        brief = kwargs["brief"]
        strategy = kwargs["selected_strategy"]
        return f"""Write a review guide for a synthesized {brief.get('name', 'artifact')}.

Strategy used: {strategy['name']}
What to check:
- Preserved items are faithfully included
- Adapted items are correctly transformed
- Discarded items are truly removed
- No content conflicts remain"""

    def _call_llm(self, prompt: str) -> str:
        """Send a prompt to the LLM. See LLMAnalyzer._call_llm() for guidance."""
        raise NotImplementedError(
            "LLMContentSynthesizer._call_llm() is not yet connected to an LLM API. "
            "See LLMAnalyzer._call_llm() docstring for integration instructions."
        )
