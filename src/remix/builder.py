from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from remix.utils import DEFAULT_PROTOCOL_VERSION as SUPPORTED_PROTOCOL_VERSION, compact_excerpt, generate_id, keyword_overlap, markdown_bullets, skillify, slugify, top_words, utc_now_iso


# ---------------------------------------------------------------------------
# HeuristicContentSynthesizer -- the core enhancement
# ---------------------------------------------------------------------------

class HeuristicContentSynthesizer:
    """Heuristic-based content synthesizer that produces rich structured outlines.

    Implements the ContentSynthesizer protocol from interfaces.py without
    requiring any external LLM API. Instead, it uses structural analysis of
    source units, strategy decisions, and keyword overlap to produce:

    1. A content outline with merged sections, source-tagged bullet points,
       conflict markers, and adaptation notes.
    2. A synthesis guide with explicit operator instructions for completing
       the fusion.
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
        """Generate a structured content outline from analysis data.

        The outline contains:
        - Merged section headings derived from source structures
        - Source-tagged bullet points of key content per section
        - CONFLICT markers where sources cover the same topic differently
        - ADAPT markers where the strategy says to adapt a pattern
        """
        source_index = {s["source_id"]: s for s in normalized_sources}
        analysis_index = {r["source_id"]: r for r in analysis_reports}
        strategy_source_ids = set(selected_strategy.get("source_ids", []))

        # Phase 1: Collect all conceptual units organized by topic
        topic_buckets = self._cluster_units_by_topic(
            normalized_sources, strategy_source_ids
        )

        # Phase 2: Classify units per strategy (preserve / discard / adapt)
        classified = self._classify_units(
            topic_buckets, selected_strategy, source_index, analysis_index
        )

        # Phase 3: Render the outline
        lines: List[str] = []
        lines.append(f"# {brief.get('name', 'Remixed Artifact')} -- Content Outline")
        lines.append("")
        lines.append(f"> Target: `{target_profile['profile_id']}` | "
                      f"Strategy: `{selected_strategy['strategy_id']}` | "
                      f"Sources: {', '.join(selected_strategy['source_ids'])}")
        lines.append("")

        # Purpose section from brief
        lines.append("## Purpose")
        lines.append("")
        lines.append(brief.get("target_job", "Deliver the requested outcome."))
        lines.append("")
        if brief.get("success_criteria"):
            lines.append("**Success criteria:**")
            for criterion in brief["success_criteria"]:
                lines.append(f"- {criterion}")
            lines.append("")

        # Strategy summary
        lines.append("## Strategy Decisions")
        lines.append("")
        lines.append("### Preserve")
        for item in selected_strategy.get("preserve", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### Discard")
        for item in selected_strategy.get("discard", []):
            lines.append(f"- ~~{item}~~")
        lines.append("")
        lines.append("### Adapt")
        for item in selected_strategy.get("adapt", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append("### Introduce (new)")
        for item in selected_strategy.get("introduce", []):
            lines.append(f"- {item}")
        lines.append("")

        # Merged content sections
        lines.append("---")
        lines.append("")
        lines.append("## Synthesized Content Sections")
        lines.append("")

        for topic, entries in classified.items():
            lines.append(f"### {topic}")
            lines.append("")

            # Check for conflicts (multiple sources covering same topic)
            contributing_sources = list({e["source_id"] for e in entries})
            if len(contributing_sources) > 1:
                lines.append(
                    f"<!-- CONFLICT: Multiple sources cover this topic: "
                    f"{', '.join(contributing_sources)}. Manual fusion needed. -->"
                )
                lines.append("")

            for entry in entries:
                status_tag = entry["status"].upper()
                source_tag = f"[{entry['source_id']}]"

                if entry["status"] == "discard":
                    lines.append(f"- ~~{source_tag} {entry['summary']}~~ `{status_tag}`")
                elif entry["status"] == "adapt":
                    lines.append(f"- {source_tag} {entry['summary']} `{status_tag}`")
                    if entry.get("adaptation_note"):
                        lines.append(f"  - *Adaptation:* {entry['adaptation_note']}")
                else:
                    lines.append(f"- {source_tag} {entry['summary']} `PRESERVE`")

            lines.append("")

        # Source strengths summary
        lines.append("## Source Contribution Summary")
        lines.append("")
        for source_id in selected_strategy["source_ids"]:
            report = analysis_index.get(source_id, {})
            source = source_index.get(source_id, {})
            lines.append(f"### {source_id}")
            lines.append("")
            lines.append(f"**Scope:** {report.get('scope', 'unknown')}")
            lines.append("")
            if report.get("strengths"):
                lines.append("**Strengths:**")
                for s in report["strengths"][:4]:
                    lines.append(f"- {s}")
                lines.append("")
            if report.get("reusable_patterns"):
                lines.append("**Reusable patterns:**")
                for p in report["reusable_patterns"][:5]:
                    lines.append(f"- `{p['kind']}` **{p['name']}** ({p['unit_id']})")
                lines.append("")
            if report.get("weaknesses"):
                lines.append("**Weaknesses (to mitigate):**")
                for w in report["weaknesses"][:3]:
                    lines.append(f"- {w}")
                lines.append("")

        # Risks and open questions
        if selected_strategy.get("risks"):
            lines.append("## Risks")
            lines.append("")
            for risk in selected_strategy["risks"]:
                lines.append(f"- {risk}")
            lines.append("")

        return "\n".join(lines)

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
        """Generate a synthesis guide for the LLM operator.

        The guide includes:
        - Which sections need manual fusion
        - What content from each source goes where
        - What to preserve verbatim vs what to rewrite
        - Priority order based on source rankings
        """
        source_index = {s["source_id"]: s for s in normalized_sources}
        analysis_index = {r["source_id"]: r for r in analysis_reports}
        rankings = comparison.get("source_rankings", [])

        lines: List[str] = []
        lines.append("# Synthesis Guide")
        lines.append("")
        lines.append(f"> For: **{brief.get('name', 'Remixed Artifact')}** | "
                      f"Profile: `{target_profile['profile_id']}` | "
                      f"Strategy: `{selected_strategy['name']}`")
        lines.append("")
        lines.append("This guide provides explicit instructions for completing the "
                      "content synthesis. Use it alongside the content outline.")
        lines.append("")

        # Section 1: Priority order
        lines.append("## 1. Source Priority Order")
        lines.append("")
        lines.append("When sources conflict, prefer content from higher-ranked sources.")
        lines.append("")
        lines.append("| Rank | Source | Score | Status | Key Strengths |")
        lines.append("| --- | --- | --- | --- | --- |")
        for i, ranking in enumerate(rankings, 1):
            sid = ranking["source_id"]
            score = ranking.get("overall_score", 0)
            status = ranking.get("status", "unknown")
            strengths = ranking.get("rationales", {}).get("strengths", [])
            strength_text = "; ".join(strengths[:2]) if strengths else "none noted"
            lines.append(f"| {i} | {sid} | {score:.2f} | {status} | {strength_text} |")
        lines.append("")

        # Section 2: Section-by-section instructions
        lines.append("## 2. Section-by-Section Instructions")
        lines.append("")

        strategy_source_ids = set(selected_strategy.get("source_ids", []))
        topic_buckets = self._cluster_units_by_topic(normalized_sources, strategy_source_ids)
        classified = self._classify_units(
            topic_buckets, selected_strategy, source_index, analysis_index
        )

        for topic, entries in classified.items():
            contributing_sources = list({e["source_id"] for e in entries})
            preserve_entries = [e for e in entries if e["status"] == "preserve"]
            adapt_entries = [e for e in entries if e["status"] == "adapt"]
            discard_entries = [e for e in entries if e["status"] == "discard"]

            lines.append(f"### {topic}")
            lines.append("")

            if len(contributing_sources) > 1:
                lines.append(f"**ACTION REQUIRED: MANUAL FUSION** -- "
                              f"{len(contributing_sources)} sources contribute to this section.")
                lines.append("")

                # Determine which source ranks higher for conflict resolution
                source_rank = {
                    r["source_id"]: i
                    for i, r in enumerate(rankings, 1)
                }
                sorted_contributors = sorted(
                    contributing_sources,
                    key=lambda sid: source_rank.get(sid, 999)
                )
                lines.append(f"**Recommended lead source:** `{sorted_contributors[0]}`")
                lines.append("")
            elif len(contributing_sources) == 1:
                lines.append(f"**Single source:** `{contributing_sources[0]}` -- "
                              "straightforward extraction.")
                lines.append("")

            if preserve_entries:
                lines.append("**Preserve verbatim (or near-verbatim):**")
                for e in preserve_entries:
                    lines.append(f"- From `{e['source_id']}`: {e['summary']}")
                lines.append("")

            if adapt_entries:
                lines.append("**Adapt (rewrite to fit target):**")
                for e in adapt_entries:
                    note = e.get("adaptation_note", "Rewrite to match target profile conventions.")
                    lines.append(f"- From `{e['source_id']}`: {e['summary']}")
                    lines.append(f"  - *How to adapt:* {note}")
                lines.append("")

            if discard_entries:
                lines.append("**Discard (do not include):**")
                for e in discard_entries:
                    lines.append(f"- ~~From `{e['source_id']}`: {e['summary']}~~")
                lines.append("")

        # Section 3: Verbatim preservation checklist
        lines.append("## 3. Verbatim Preservation Checklist")
        lines.append("")
        lines.append("These items from the strategy MUST appear in the final output:")
        lines.append("")
        for item in selected_strategy.get("preserve", []):
            lines.append(f"- [ ] {item}")
        lines.append("")

        # Section 4: Adaptation checklist
        lines.append("## 4. Adaptation Checklist")
        lines.append("")
        lines.append("These items need transformation before inclusion:")
        lines.append("")
        for item in selected_strategy.get("adapt", []):
            lines.append(f"- [ ] {item}")
        lines.append("")

        # Section 5: Quality gates
        lines.append("## 5. Quality Gates Before Finalizing")
        lines.append("")
        lines.append("- [ ] All `CONFLICT` markers in the content outline are resolved")
        lines.append("- [ ] All `ADAPT` items have been rewritten for the target profile")
        lines.append("- [ ] No `DISCARD` content leaked into the final document")
        lines.append("- [ ] Success criteria from the brief are addressed:")
        for criterion in brief.get("success_criteria", ["(none specified)"]):
            lines.append(f"  - [ ] {criterion}")
        lines.append("- [ ] Source attribution is accurate in provenance.json")
        lines.append("")

        # Section 6: Risks to watch for
        if selected_strategy.get("risks"):
            lines.append("## 6. Risks to Watch For")
            lines.append("")
            for risk in selected_strategy["risks"]:
                lines.append(f"- {risk}")
            lines.append("")

        return "\n".join(lines)

    # ---- internal helpers ----

    def _cluster_units_by_topic(
        self,
        normalized_sources: Sequence[Dict[str, Any]],
        strategy_source_ids: set,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group conceptual units from all selected sources by topic.

        Uses a combination of:
        - Heading-level grouping (units with kind=heading keep their name as topic)
        - Keyword-based clustering (units with overlapping keywords get merged)
        - Kind-based fallback (code units -> "Code Components", etc.)
        """
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for source in normalized_sources:
            sid = source["source_id"]
            if sid not in strategy_source_ids:
                continue
            for unit in source.get("units", []):
                topic = self._topic_for_unit(unit)
                buckets[topic].append({
                    "source_id": sid,
                    "unit_id": unit["unit_id"],
                    "kind": unit["kind"],
                    "name": unit["name"],
                    "summary": unit.get("summary", unit["name"]),
                })

        # Merge small buckets into "Other Content"
        merged: Dict[str, List[Dict[str, Any]]] = {}
        overflow: List[Dict[str, Any]] = []
        for topic, entries in buckets.items():
            if len(entries) >= 1 and len(topic) > 2:
                merged[topic] = entries
            else:
                overflow.extend(entries)
        if overflow:
            merged["Other Content"] = overflow

        return merged

    def _topic_for_unit(self, unit: Dict[str, Any]) -> str:
        """Determine the topic name for a conceptual unit."""
        kind = unit["kind"]
        name = unit["name"]

        if kind == "heading":
            # Use the heading text as the topic
            cleaned = re.sub(r"^#+\s*", "", name).strip()
            return cleaned or "Overview"
        if kind in ("class", "function", "export"):
            return "Code Components"
        if kind == "json-key":
            return "Data Structure"
        if kind == "file":
            # Group files by directory or extension
            parts = name.split("/")
            if len(parts) > 1:
                return f"Files: {parts[0]}"
            return "Files"
        if kind == "paragraph":
            # Use first few words as topic
            words = name.split()[:4]
            return " ".join(words) if words else "Content"
        return "General"

    def _classify_units(
        self,
        topic_buckets: Dict[str, List[Dict[str, Any]]],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
        analysis_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Classify each unit as preserve/discard/adapt based on strategy."""
        preserve_keywords = set()
        for text in selected_strategy.get("preserve", []):
            preserve_keywords.update(w.lower() for w in re.findall(r"\w+", text) if len(w) > 3)

        discard_keywords = set()
        for text in selected_strategy.get("discard", []):
            discard_keywords.update(w.lower() for w in re.findall(r"\w+", text) if len(w) > 3)

        adapt_names = set()
        for text in selected_strategy.get("adapt", []):
            # "Adapt X from source-Y" -> extract X
            match = re.match(r"Adapt\s+(.+?)\s+from\s+", text)
            if match:
                adapt_names.add(match.group(1).lower())
            adapt_names.update(w.lower() for w in re.findall(r"\w+", text) if len(w) > 3)

        classified: Dict[str, List[Dict[str, Any]]] = {}
        for topic, entries in topic_buckets.items():
            classified_entries = []
            for entry in entries:
                entry_words = set(
                    w.lower() for w in re.findall(r"\w+", entry["summary"]) if len(w) > 3
                )
                name_lower = entry["name"].lower()

                # Check adapt first (most specific)
                if name_lower in adapt_names or (adapt_names & entry_words):
                    status = "adapt"
                    # Generate adaptation note
                    report = analysis_index.get(entry["source_id"], {})
                    note = self._generate_adaptation_note(
                        entry, selected_strategy, source_index.get(entry["source_id"], {})
                    )
                elif discard_keywords & entry_words and not (preserve_keywords & entry_words):
                    status = "discard"
                    note = None
                else:
                    status = "preserve"
                    note = None

                classified_entries.append({
                    **entry,
                    "status": status,
                    "adaptation_note": note,
                })
            classified[topic] = classified_entries

        return classified

    def _generate_adaptation_note(
        self,
        entry: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source: Dict[str, Any],
    ) -> str:
        """Generate a specific adaptation note for a unit."""
        kind = entry["kind"]
        target_shape = selected_strategy.get("expected_output_shape", [])

        if kind in ("class", "function", "export"):
            return (
                f"Refactor `{entry['name']}` to fit the target artifact shape "
                f"({', '.join(target_shape)}). Preserve core logic, update interfaces."
            )
        if kind == "heading":
            return (
                f"Rewrite section '{entry['name']}' to align with the target profile's "
                "conventions and terminology."
            )
        if kind == "json-key":
            return (
                f"Transform the `{entry['name']}` data structure to match the "
                "target schema requirements."
            )
        return (
            f"Adapt this content from {entry['source_id']} to match the target "
            "profile's style and requirements."
        )


class TargetBuilder:
    def __init__(self, validator, *, content_synthesizer=None) -> None:
        self.validator = validator
        self.content_synthesizer = content_synthesizer or HeuristicContentSynthesizer()

    def build(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        build_plan: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        normalized_sources: Sequence[Dict[str, Any]],
        analysis_reports: Sequence[Dict[str, Any]],
        comparison: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        source_index = {source["source_id"]: source for source in normalized_sources}
        analysis_index = {report["source_id"]: report for report in analysis_reports}
        outputs: List[Dict[str, Any]] = []

        if target_profile["profile_id"] == "compound":
            bundle_readme = [
                f"# {brief.get('name', 'Compound Remix Bundle')}",
                "",
                "## Child Profiles",
                markdown_bullets([child["profile_id"] for child in target_profile.get("child_profiles", [])]),
            ]
            workspace.write_text(workspace.remixed_output_dir / "docs" / "compound_bundle.md", "\n".join(bundle_readme))
            outputs.append({"type": "document", "path": "docs/compound_bundle.md", "summary": "Compound bundle overview."})
            for child_profile in target_profile.get("child_profiles", []):
                child_outputs = self._build_profile_outputs(
                    workspace=workspace,
                    brief=brief,
                    target_profile=child_profile,
                    selected_strategy=selected_strategy,
                    source_index=source_index,
                    analysis_index=analysis_index,
                )
                outputs.extend(child_outputs)
        else:
            outputs.extend(
                self._build_profile_outputs(
                    workspace=workspace,
                    brief=brief,
                    target_profile=target_profile,
                    selected_strategy=selected_strategy,
                    source_index=source_index,
                    analysis_index=analysis_index,
                )
            )

        # Generate structured content outline and synthesis guide
        content_outline = self.content_synthesizer.generate_content_outline(
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
            normalized_sources=normalized_sources,
            analysis_reports=analysis_reports,
        )
        workspace.write_text(
            workspace.remixed_output_dir / "docs" / "content_outline.md",
            content_outline,
        )
        outputs.append({
            "type": "content-outline",
            "path": "docs/content_outline.md",
            "summary": "Structured content outline with source-tagged sections, conflict markers, and adaptation notes.",
        })

        # Build comparison dict for the synthesis guide if not provided
        if comparison is None:
            comparison = {"source_rankings": [], "complementarity": []}

        synthesis_guide = self.content_synthesizer.generate_synthesis_guide(
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
            normalized_sources=normalized_sources,
            analysis_reports=analysis_reports,
            comparison=comparison,
        )
        workspace.write_text(
            workspace.remixed_output_dir / "synthesis_guide.md",
            synthesis_guide,
        )
        outputs.append({
            "type": "synthesis-guide",
            "path": "synthesis_guide.md",
            "summary": "Operator guide for completing content synthesis with priority order and section instructions.",
        })

        docs_outputs = self._build_shared_docs(
            workspace=workspace,
            brief=brief,
            selected_strategy=selected_strategy,
            target_profile=target_profile,
            source_index=source_index,
            analysis_index=analysis_index,
        )
        outputs.extend(docs_outputs)

        influence_map = self._build_source_influence_map(outputs, selected_strategy["source_ids"], source_index)
        workspace.write_json(workspace.source_influence_map_path, influence_map)
        provenance = self._build_provenance(influence_map, normalized_sources)
        workspace.write_json(workspace.provenance_path, provenance)

        artifact_manifest = {
            "artifact_id": generate_id("artifact"),
            "generated_at": utc_now_iso(),
            "name": brief.get("name") or f"remixed-{target_profile['profile_id']}",
            "target_profile": target_profile["profile_id"],
            "packaging_profile": target_profile.get("packaging_profile"),
            "transformation_mode": brief.get("transformation_mode", "consolidate"),
            "selected_strategy_id": selected_strategy["strategy_id"],
            "source_ids": selected_strategy["source_ids"],
            "outputs": outputs,
            "governor_ready": bool(brief.get("governor_ready")),
        }
        workspace.write_json(workspace.artifact_manifest_path, artifact_manifest)

        release_manifest = {
            "bundle_name": artifact_manifest["name"],
            "created_at": artifact_manifest["generated_at"],
            "artifact_manifest": str(workspace.artifact_manifest_path.relative_to(workspace.root)),
            "provenance": str(workspace.provenance_path.relative_to(workspace.root)),
            "outputs": outputs,
        }
        workspace.write_json(workspace.release_bundle_dir / "release_manifest.json", release_manifest)

        if target_profile["profile_id"] == "skill" and brief.get("governor_ready"):
            proposal = self._build_governor_candidate(workspace=workspace, artifact_manifest=artifact_manifest)
            workspace.write_json(workspace.release_bundle_dir / "governor_candidate" / "skill_proposal.json", proposal)

        if target_profile["profile_id"] != "skill" and build_plan.get("companion_skill_wrapper_needed"):
            wrapper = self._build_companion_skill_wrapper(brief=brief, target_profile=target_profile, selected_strategy=selected_strategy)
            workspace.write_json(workspace.release_bundle_dir / "companion_skill_wrapper.json", wrapper)

        return {
            "artifact_manifest": artifact_manifest,
            "provenance": provenance,
            "outputs": outputs,
            "source_influence_map": influence_map,
        }

    def _build_profile_outputs(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
        analysis_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if target_profile["profile_id"] == "skill":
            return self._build_skill_profile(
                workspace=workspace,
                brief=brief,
                selected_strategy=selected_strategy,
                source_index=source_index,
                analysis_index=analysis_index,
            )
        if target_profile["profile_id"] == "protocol":
            return self._build_protocol_profile(
                workspace=workspace,
                brief=brief,
                selected_strategy=selected_strategy,
                source_index=source_index,
            )
        if target_profile["profile_id"] == "module":
            return self._build_module_profile(
                workspace=workspace,
                brief=brief,
                target_profile=target_profile,
                selected_strategy=selected_strategy,
                source_index=source_index,
            )
        if target_profile["profile_id"] == "feature":
            return self._build_feature_profile(
                workspace=workspace,
                brief=brief,
                selected_strategy=selected_strategy,
                source_index=source_index,
            )
        if target_profile["profile_id"] == "product":
            return self._build_product_profile(
                workspace=workspace,
                brief=brief,
                selected_strategy=selected_strategy,
                source_index=source_index,
            )
        return []

    def _build_skill_profile(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
        analysis_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        name = brief.get("name") or "Remixed Skill"
        skill_id = brief.get("skill_id") or skillify(name)
        manifest = {
            "schema_name": "SkillManifest",
            "schema_version": "1.0.0",
            "protocol_version": SUPPORTED_PROTOCOL_VERSION,
            "skill_id": skill_id,
            "name": name,
            "version": brief.get("version", "0.1.0"),
            "description": brief.get("target_job", "Remixed skill artifact."),
            "governance": {
                "mode": "standalone",
                "official_status": "local",
            },
            "capability": {
                "level": "native",
                "summary": brief.get("capability_summary", "Remixed skill output."),
                "declared_interfaces": brief.get("declared_interfaces", ["remix.execute", "remix.review"]),
            },
            "compatibility": {
                "min_protocol_version": SUPPORTED_PROTOCOL_VERSION,
                "max_protocol_version": SUPPORTED_PROTOCOL_VERSION,
            },
            "metadata": {
                "generated_by": "remix",
                "selected_strategy_id": selected_strategy["strategy_id"],
                "source_ids": selected_strategy["source_ids"],
            },
        }
        self.validator.validate_manifest(manifest)
        workspace.write_json(workspace.remixed_output_dir / "skill" / "manifest.json", manifest)

        # Collect workflows from analysis reports
        workflows = []
        for source_id in selected_strategy["source_ids"]:
            workflows.extend(analysis_index[source_id]["workflow"][:2])

        # Collect reusable patterns from analysis
        all_patterns: List[Dict[str, Any]] = []
        for source_id in selected_strategy["source_ids"]:
            report = analysis_index[source_id]
            for pattern in report.get("reusable_patterns", [])[:4]:
                all_patterns.append({**pattern, "source_id": source_id})

        # Collect units from sources for richer content
        all_units_by_source: Dict[str, List[Dict[str, Any]]] = {}
        for source_id in selected_strategy["source_ids"]:
            source = source_index[source_id]
            all_units_by_source[source_id] = source.get("units", [])[:10]

        # Build enriched SKILL.md
        skill_lines: List[str] = [
            f"# {name}",
            "",
            "## Purpose",
            "",
            brief.get("target_job", "Deliver the requested skill outcome."),
            "",
        ]

        # Success criteria (if present)
        if brief.get("success_criteria"):
            skill_lines.append("### Success Criteria")
            skill_lines.append("")
            for criterion in brief["success_criteria"]:
                skill_lines.append(f"- {criterion}")
            skill_lines.append("")

        # Source overview with contribution details
        skill_lines.extend([
            "## Sources & Contributions",
            "",
        ])
        for source_id in selected_strategy["source_ids"]:
            report = analysis_index[source_id]
            skill_lines.append(f"### {source_id}")
            skill_lines.append("")
            skill_lines.append(f"**Scope:** {report.get('scope', 'unknown')}")
            skill_lines.append("")
            if report.get("strengths"):
                skill_lines.append("**Key contributions:**")
                for s in report["strengths"][:3]:
                    skill_lines.append(f"- {s}")
                skill_lines.append("")
            if report.get("reusable_patterns"):
                skill_lines.append("**Reusable elements:**")
                for p in report["reusable_patterns"][:4]:
                    skill_lines.append(f"- `{p['kind']}` **{p['name']}**")
                skill_lines.append("")

        # Workflow section with actual content
        skill_lines.extend([
            "## Workflow",
            "",
        ])
        unique_workflows = list(dict.fromkeys(workflows))[:6]
        if unique_workflows:
            skill_lines.append(markdown_bullets(unique_workflows))
        else:
            skill_lines.append("- (Derive workflow from source content during synthesis)")
        skill_lines.append("")

        # Content map -- key conceptual units organized by kind
        skill_lines.extend([
            "## Content Map",
            "",
            "The following conceptual units from the sources form the basis of this skill:",
            "",
        ])
        units_by_kind: Dict[str, List[str]] = defaultdict(list)
        for source_id, units in all_units_by_source.items():
            for unit in units:
                kind = unit["kind"]
                summary = unit.get("summary", unit["name"])
                units_by_kind[kind].append(
                    f"`[{source_id}]` **{unit['name']}**: {compact_excerpt(summary, max_chars=120)}"
                )
        for kind, items in units_by_kind.items():
            skill_lines.append(f"### {kind.replace('-', ' ').title()}s")
            skill_lines.append("")
            for item in items[:6]:
                skill_lines.append(f"- {item}")
            skill_lines.append("")

        # Strategy decisions relevant to this skill
        skill_lines.extend([
            "## Strategy Decisions",
            "",
            f"**Strategy:** `{selected_strategy['strategy_id']}` ({selected_strategy['name']})",
            "",
            "### Preserved",
            markdown_bullets(selected_strategy.get("preserve", ["(none)"])[:5]),
            "",
            "### Adapted",
            markdown_bullets(selected_strategy.get("adapt", ["(none)"])[:5]),
            "",
            "### Discarded",
            markdown_bullets(selected_strategy.get("discard", ["(none)"])[:5]),
            "",
            "### Introduced",
            markdown_bullets(selected_strategy.get("introduce", ["(none)"])[:3]),
            "",
        ])

        # Constraints
        skill_lines.extend([
            "## Constraints",
            "",
            markdown_bullets(_brief_constraints(brief)),
            "",
        ])

        # Verification
        skill_lines.extend([
            "## Verification",
            "",
            markdown_bullets(
                [
                    "Protocol-compatible manifest validation",
                    "Scenario smoke checks",
                    "Source attribution sanity checks",
                ]
            ),
            "",
        ])

        # Provenance
        skill_lines.extend([
            "## Provenance",
            "",
            "See `../provenance.json` and `../docs/strategy.md` for source influence details.",
            "",
            "See `../docs/content_outline.md` for the full structured content outline with "
            "source-tagged sections and conflict markers.",
            "",
            "See `../synthesis_guide.md` for step-by-step instructions on completing "
            "the content synthesis.",
            "",
        ])

        # Handoff
        skill_lines.extend([
            "## Handoff",
            "",
            "This package is ready for local review and optional governed submission "
            "through the release bundle.",
        ])

        skill_md = "\n".join(skill_lines)
        workspace.write_text(workspace.remixed_output_dir / "skill" / "SKILL.md", skill_md)
        workspace.write_text(
            workspace.remixed_output_dir / "skill" / "tests.md",
            "\n".join(
                [
                    "# Skill Test Tasks",
                    "",
                    markdown_bullets(brief.get("recommended_test_tasks", _default_test_tasks(brief, selected_strategy))),
                ]
            ),
        )
        return [
            {"type": "skill-manifest", "path": "skill/manifest.json", "summary": "Protocol-compatible skill manifest."},
            {"type": "skill-markdown", "path": "skill/SKILL.md", "summary": "Skill instructions and workflow."},
            {"type": "skill-tests", "path": "skill/tests.md", "summary": "Scenario tasks for skill verification."},
        ]

    def _build_protocol_profile(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        title = brief.get("name", "Remixed Protocol")
        properties = {}
        example = {}
        for source_id in selected_strategy["source_ids"]:
            for unit in source_index[source_id].get("units", [])[:4]:
                key = slugify(unit["name"], separator="_")
                properties[key] = {
                    "type": "string",
                    "description": compact_excerpt(unit.get("summary", ""), max_chars=100),
                }
                example[key] = unit["name"]
        if not properties:
            properties["payload"] = {"type": "string", "description": "Default payload value."}
            example["payload"] = "value"

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": title,
            "type": "object",
            "description": brief.get("target_job", "Remixed protocol bundle."),
            "properties": properties,
            "required": list(properties.keys())[: min(2, len(properties))],
            "additionalProperties": False,
        }
        workspace.write_json(workspace.remixed_output_dir / "protocol" / "schemas" / "remixed.schema.json", schema)
        workspace.write_json(workspace.remixed_output_dir / "protocol" / "examples" / "example.json", example)
        compatibility = "\n".join(
            [
                "# Compatibility Matrix",
                "",
                "| Dimension | Status |",
                "| --- | --- |",
                "| Structural schema | defined |",
                "| Example payload | provided |",
                "| Migration guidance | included in docs |",
            ]
        )
        workspace.write_text(workspace.remixed_output_dir / "protocol" / "compatibility_matrix.md", compatibility)
        return [
            {"type": "protocol-schema", "path": "protocol/schemas/remixed.schema.json", "summary": "Remixed schema bundle."},
            {"type": "protocol-example", "path": "protocol/examples/example.json", "summary": "Example payload for the remixed protocol."},
            {"type": "protocol-compatibility", "path": "protocol/compatibility_matrix.md", "summary": "Protocol compatibility notes."},
        ]

    def _build_module_profile(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        packaging_profile = target_profile.get("packaging_profile", "python-package")
        module_name = slugify(brief.get("module_name", brief.get("name", "remix_module")), separator="_")
        if packaging_profile == "npm-package":
            package_json = {
                "name": slugify(brief.get("name", module_name)),
                "version": brief.get("version", "0.1.0"),
                "description": brief.get("target_job", "Remixed module bundle."),
                "main": "src/index.js",
            }
            workspace.write_json(workspace.remixed_output_dir / "module" / "package.json", package_json)
            workspace.write_text(
                workspace.remixed_output_dir / "module" / "src" / "index.js",
                "\n".join(
                    [
                        "function getBlueprint() {",
                        "  return {",
                        f"    strategyId: '{selected_strategy['strategy_id']}',",
                        f"    sources: {selected_strategy['source_ids']!r},",
                        "  };",
                        "}",
                        "",
                        "module.exports = { getBlueprint };",
                    ]
                ),
            )
            outputs = [
                {"type": "module-package", "path": "module/package.json", "summary": "NPM packaging metadata."},
                {"type": "module-source", "path": "module/src/index.js", "summary": "Module entrypoint."},
            ]
        else:
            pyproject = "\n".join(
                [
                    "[build-system]",
                    'requires = ["setuptools>=68", "wheel"]',
                    'build-backend = "setuptools.build_meta"',
                    "",
                    "[project]",
                    f'name = "{slugify(brief.get("name", module_name))}"',
                    f'version = "{brief.get("version", "0.1.0")}"',
                    f'description = "{brief.get("target_job", "Remixed module bundle.")}"',
                    'requires-python = ">=3.9"',
                    "",
                    "[tool.setuptools]",
                    'package-dir = {"" = "src"}',
                ]
            )
            workspace.write_text(workspace.remixed_output_dir / "module" / "pyproject.toml", pyproject)
            module_dir = workspace.remixed_output_dir / "module" / "src" / module_name
            workspace.write_text(
                module_dir / "__init__.py",
                "\n".join(
                    [
                        '"""Generated by remix."""',
                        "",
                        "from __future__ import annotations",
                        "",
                        "def get_blueprint() -> dict:",
                        "    return {",
                        f'        "strategy_id": "{selected_strategy["strategy_id"]}",',
                        f'        "source_ids": {selected_strategy["source_ids"]!r},',
                        f'        "summary": "{compact_excerpt(brief.get("target_job", "Remixed module bundle."), max_chars=120)}",',
                        "    }",
                    ]
                ),
            )
            workspace.write_text(
                workspace.remixed_output_dir / "module" / "tests" / f"test_{module_name}.py",
                "\n".join(
                    [
                        "from __future__ import annotations",
                        "",
                        f"from {module_name} import get_blueprint",
                        "",
                        "",
                        "def test_blueprint_contains_strategy_id() -> None:",
                        '    assert "strategy_id" in get_blueprint()',
                    ]
                ),
            )
            outputs = [
                {"type": "module-package", "path": "module/pyproject.toml", "summary": "Python package metadata."},
                {"type": "module-source", "path": f"module/src/{module_name}/__init__.py", "summary": "Module entrypoint."},
                {"type": "module-test", "path": f"module/tests/test_{module_name}.py", "summary": "Basic module test."},
            ]
        readme = "\n".join(
            [
                f"# {brief.get('name', 'Remixed Module')}",
                "",
                "## Source Inputs",
                markdown_bullets(selected_strategy["source_ids"]),
                "",
                "## Intended Interfaces",
                markdown_bullets(brief.get("declared_interfaces", ["get_blueprint"])),
            ]
        )
        workspace.write_text(workspace.remixed_output_dir / "module" / "README.md", readme)
        outputs.append({"type": "module-readme", "path": "module/README.md", "summary": "Module overview and intended interfaces."})
        return outputs

    def _build_feature_profile(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        spec = "\n".join(
            [
                f"# {brief.get('name', 'Remixed Feature')}",
                "",
                "## Goal",
                brief.get("target_job", "Deliver the requested feature outcome."),
                "",
                "## Preserved Source Ideas",
                markdown_bullets(selected_strategy["preserve"]),
                "",
                "## Adapted Ideas",
                markdown_bullets(selected_strategy["adapt"]),
            ]
        )
        rollout = "\n".join(
            [
                "# Rollout Plan",
                "",
                "## Staged Rollout",
                markdown_bullets(
                    [
                        "Launch behind a flag or staged availability mechanism.",
                        "Collect baseline metrics before rollout.",
                    ]
                ),
                "",
                "## Rollback",
                markdown_bullets(
                    [
                        "Prepare rollback triggers and ownership contacts.",
                        "Define failure thresholds that trigger automatic rollback.",
                    ]
                ),
            ]
        )
        instrumentation = "\n".join(
            [
                "# Instrumentation Plan",
                "",
                markdown_bullets(
                    [
                        "Record adoption, failure, and latency signals.",
                        "Track acceptance criteria coverage in telemetry.",
                        "Link rollout signals back to selected source assumptions.",
                    ]
                ),
            ]
        )
        acceptance = "\n".join(
            [
                "# Acceptance Criteria",
                "",
                markdown_bullets(brief.get("success_criteria", ["Feature behavior matches the remixed strategy."])),
            ]
        )
        workspace.write_text(workspace.remixed_output_dir / "feature" / "spec.md", spec)
        workspace.write_text(workspace.remixed_output_dir / "feature" / "rollout_plan.md", rollout)
        workspace.write_text(workspace.remixed_output_dir / "feature" / "instrumentation_plan.md", instrumentation)
        workspace.write_text(workspace.remixed_output_dir / "feature" / "acceptance_criteria.md", acceptance)
        return [
            {"type": "feature-spec", "path": "feature/spec.md", "summary": "Feature specification."},
            {"type": "feature-rollout", "path": "feature/rollout_plan.md", "summary": "Rollout and rollback plan."},
            {"type": "feature-instrumentation", "path": "feature/instrumentation_plan.md", "summary": "Instrumentation plan."},
            {"type": "feature-acceptance", "path": "feature/acceptance_criteria.md", "summary": "Acceptance criteria."},
        ]

    def _build_product_profile(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        prd = "\n".join(
            [
                f"# {brief.get('name', 'Remixed Product')}",
                "",
                "## Problem",
                brief.get("target_job", "Define the target product outcome."),
                "",
                "## Success Criteria",
                markdown_bullets(brief.get("success_criteria", ["Deliver a coherent product plan."])),
                "",
                "## Source Inputs",
                markdown_bullets(selected_strategy["source_ids"]),
            ]
        )
        capability_map = "\n".join(
            [
                "# Capability Map",
                "",
                markdown_bullets(selected_strategy["preserve"] + selected_strategy["adapt"]),
            ]
        )
        roadmap = "\n".join(
            [
                "# Roadmap",
                "",
                markdown_bullets(
                    [
                        "Phase 1: align on preserved capabilities and target constraints.",
                        "Phase 2: implement remixed core flow and instrumentation.",
                        "Phase 3: validate adoption and refine based on feedback.",
                    ]
                ),
            ]
        )
        open_questions = "\n".join(
            [
                "# Open Questions",
                "",
                markdown_bullets(
                    [
                        "Which native authority will own final publication?",
                        "Which dependencies need explicit buy-in before rollout?",
                        "Which source assumptions remain unvalidated?",
                    ]
                ),
            ]
        )
        workspace.write_text(workspace.remixed_output_dir / "product" / "PRD.md", prd)
        workspace.write_text(workspace.remixed_output_dir / "product" / "capability_map.md", capability_map)
        workspace.write_text(workspace.remixed_output_dir / "product" / "roadmap.md", roadmap)
        workspace.write_text(workspace.remixed_output_dir / "product" / "open_questions.md", open_questions)
        return [
            {"type": "product-prd", "path": "product/PRD.md", "summary": "Product requirements document."},
            {"type": "product-capability-map", "path": "product/capability_map.md", "summary": "Capability map."},
            {"type": "product-roadmap", "path": "product/roadmap.md", "summary": "Roadmap."},
            {"type": "product-open-questions", "path": "product/open_questions.md", "summary": "Open questions and unresolved decisions."},
        ]

    def _build_shared_docs(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        target_profile: Dict[str, Any],
        source_index: Dict[str, Dict[str, Any]],
        analysis_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        strategy_doc = "\n".join(
            [
                "# Selected Strategy",
                "",
                f"Strategy: `{selected_strategy['strategy_id']}`",
                "",
                "## Preserve",
                markdown_bullets(selected_strategy["preserve"]),
                "",
                "## Discard",
                markdown_bullets(selected_strategy["discard"]),
                "",
                "## Adapt",
                markdown_bullets(selected_strategy["adapt"]),
                "",
                "## Introduce",
                markdown_bullets(selected_strategy["introduce"]),
            ]
        )
        release_notes = "\n".join(
            [
                "# Release Notes",
                "",
                f"Target profile: `{target_profile['profile_id']}`",
                f"Transformation mode: `{brief.get('transformation_mode', 'consolidate')}`",
                "",
                "## Key Outcomes",
                markdown_bullets(
                    [
                        f"Built a `{target_profile['profile_id']}` artifact bundle.",
                        f"Selected strategy `{selected_strategy['name']}`.",
                        "Attached provenance, audit, and verification outputs.",
                    ]
                ),
            ]
        )
        workspace.write_text(workspace.remixed_output_dir / "docs" / "strategy.md", strategy_doc)
        workspace.write_text(workspace.remixed_output_dir / "docs" / "release_notes.md", release_notes)
        return [
            {"type": "strategy-doc", "path": "docs/strategy.md", "summary": "Selected strategy and rationale."},
            {"type": "release-notes", "path": "docs/release_notes.md", "summary": "Release notes for the remixed bundle."},
        ]

    def _build_source_influence_map(
        self,
        outputs: Sequence[Dict[str, Any]],
        source_ids: Sequence[str],
        source_index: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        mapping = {
            "sources": [
                {
                    "source_id": source_id,
                    "artifact_types": source_index[source_id].get("artifact_types", []),
                    "license": source_index[source_id].get("license", "unknown"),
                }
                for source_id in source_ids
            ],
            "outputs": [],
        }
        influence_cycle = list(source_ids) or ["unknown-source"]
        for index, output in enumerate(outputs):
            mapping["outputs"].append(
                {
                    "path": output["path"],
                    "type": output["type"],
                    "source_id": influence_cycle[index % len(influence_cycle)],
                    "influence_type": "adapted" if index % 2 else "direct",
                }
            )
        return mapping

    def _build_provenance(self, influence_map: Dict[str, Any], normalized_sources: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        source_details = []
        for source in normalized_sources:
            source_details.append(
                {
                    "source_id": source["source_id"],
                    "location": source.get("location"),
                    "source_kind": source.get("source_kind"),
                    "artifact_types": source.get("artifact_types", []),
                    "license": source.get("license", "unknown"),
                    "conceptual_units": [unit["name"] for unit in source.get("units", [])[:6]],
                    "rejected_units": [risk for risk in source.get("operational_risk_signals", [])[:3]],
                }
            )
        return {
            "generated_at": utc_now_iso(),
            "sources": source_details,
            "output_influences": influence_map["outputs"],
            "uncertain_origins": [
                output["path"]
                for output in influence_map["outputs"]
                if output["influence_type"] == "adapted"
            ],
        }

    def _build_governor_candidate(self, *, workspace, artifact_manifest: Dict[str, Any]) -> Dict[str, Any]:
        proposal = {
            "schema_name": "SkillProposal",
            "schema_version": "1.0.0",
            "protocol_version": SUPPORTED_PROTOCOL_VERSION,
            "proposal_id": generate_id("proposal"),
            "skill_id": skillify(artifact_manifest["name"]),
            "created_at": utc_now_iso(),
            "proposer": {
                "authority": "local",
                "id": "remix",
            },
            "status": "candidate",
            "proposal_type": "new_skill",
            "target_version": "0.1.0",
            "change_summary": f"Candidate skill bundle for {artifact_manifest['name']}",
            "artifacts": [
                {"type": "manifest", "ref": "remixed_output/skill/manifest.json"},
                {"type": "evidence", "ref": "verification_report.md"},
                {"type": "evidence", "ref": "audit/audit_summary.md"},
            ],
            "metadata": {
                "artifact_id": artifact_manifest["artifact_id"],
            },
        }
        self.validator.validate_proposal(proposal)
        return proposal

    def _build_companion_skill_wrapper(
        self,
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "wrapper_id": generate_id("wrapper"),
            "name": f"remix-wrapper-{target_profile['profile_id']}",
            "purpose": f"Expose a skill-facing wrapper around the `{target_profile['profile_id']}` bundle.",
            "selected_strategy_id": selected_strategy["strategy_id"],
            "source_ids": selected_strategy["source_ids"],
            "governor_interface": brief.get("declared_interfaces", ["remix.bundle.review"]),
        }


class AuditComposer:
    def compose(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        normalized_sources: Sequence[Dict[str, Any]],
        comparison: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> None:
        summary = "\n".join(
            [
                "# Audit Summary",
                "",
                f"Objective: {brief.get('target_job', 'unspecified')}",
                f"Target profile: {target_profile['profile_id']}",
                f"Selected strategy: {selected_strategy['name']} ({selected_strategy['strategy_id']})",
                "",
                "## Retained Ideas",
                markdown_bullets(selected_strategy["preserve"][:3]),
                "",
                "## Rejected Ideas",
                markdown_bullets(selected_strategy["discard"][:3]),
                "",
                "## Verification Summary",
                markdown_bullets(
                    [
                        f"Overall status: {verification['overall_status']}",
                        f"Passed checks: {verification['summary']['passed']}",
                        f"Warnings: {verification['summary']['warnings']}",
                        f"Failures: {verification['summary']['failed']}",
                    ]
                ),
                "",
                "## Top Risks",
                markdown_bullets(selected_strategy["risks"][:3]),
                "",
                "## Recommendation",
                "green" if verification["overall_status"] == "pass" else "yellow" if verification["overall_status"] == "warn" else "red",
            ]
        )
        workspace.write_text(workspace.audit_summary_path, summary)
        workspace.write_json(workspace.audit_decision_log_path, {"selected_strategy": selected_strategy})

        table_lines = [
            "# Source Table",
            "",
            "| Source | Kind | Artifact Types | License | Metadata Quality | Risks |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for source in normalized_sources:
            table_lines.append(
                "| {source_id} | {kind} | {artifact_types} | {license} | {quality} | {risks} |".format(
                    source_id=source["source_id"],
                    kind=source["source_kind"],
                    artifact_types=", ".join(source.get("artifact_types", [])),
                    license=source.get("license", "unknown"),
                    quality=source.get("metadata_quality", "low"),
                    risks=len(source.get("operational_risk_signals", [])),
                )
            )
        workspace.write_text(workspace.source_table_path, "\n".join(table_lines))

        risk_lines = [
            "# Risk Register",
            "",
            "| Risk | Severity | Mitigation |",
            "| --- | --- | --- |",
        ]
        for risk in selected_strategy["risks"][:5]:
            risk_lines.append(f"| {risk} | medium | Capture the issue in verification and handoff artifacts. |")
        workspace.write_text(workspace.risk_register_path, "\n".join(risk_lines))

        evidence_index = {
            "artifacts": [
                "comparison_matrix.md",
                "comparison_scores.json",
                "strategy_options.json",
                "selected_strategy.json",
                "build_plan.json",
                "verification_report.md",
                "remixed_output/artifact_manifest.json",
                "remixed_output/provenance.json",
            ]
        }
        workspace.write_json(workspace.evidence_index_path, evidence_index)


class ReleaseManager:
    def compose_handoff(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        build_plan: Dict[str, Any],
        verification: Dict[str, Any],
    ) -> None:
        authority = build_plan["handoff_plan"]["authority"]
        handoff = "\n".join(
            [
                "# Handoff Report",
                "",
                f"Target profile: {target_profile['profile_id']}",
                f"Packaging profile: {target_profile.get('packaging_profile')}",
                f"Authority path: {authority}",
                f"Verification status: {verification['overall_status']}",
                "",
                "## Release Modes",
                markdown_bullets(build_plan["handoff_plan"]["release_modes"]),
                "",
                "## Recommended Next Actions",
                markdown_bullets(
                    [
                        "Review the audit summary and verification report.",
                        "Approve or request revision on the release bundle.",
                        f"Hand off the bundle to `{authority}` for publication or rollout.",
                    ]
                ),
            ]
        )
        workspace.write_text(workspace.handoff_report_path, handoff)


def _brief_constraints(brief: Dict[str, Any]) -> List[str]:
    constraints = []
    for key in ("constraints", "compatibility_constraints", "forbidden_licenses"):
        value = brief.get(key)
        if isinstance(value, list):
            constraints.extend(str(item) for item in value)
        elif value:
            constraints.append(str(value))
    return constraints or ["No extra constraints were provided."]


def _default_test_tasks(brief: Dict[str, Any], selected_strategy: Dict[str, Any]) -> List[str]:
    return [
        f"Exercise the bundle using the `{selected_strategy['name']}` path.",
        "Validate preserved source ideas against the generated output.",
        f"Check the bundle against `{brief.get('target_job', 'the target job')}`.",
    ]
