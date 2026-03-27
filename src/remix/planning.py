from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Sequence

from remix.utils import compact_excerpt, keyword_overlap, limited, markdown_bullets, slugify, top_words


class SourceAnalyzer:
    """Default heuristic analyzer. Implements the Analyzer protocol."""

    def analyze_sources(
        self,
        normalized_sources: Sequence[Dict[str, Any]],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        workers = min(4, max(1, len(normalized_sources)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self.analyze_source, source, brief=brief, target_profile=target_profile)
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
        brief_keywords = set(top_words(" ".join(_stringify_brief_values(brief)), limit=30))
        source_keywords = set(source.get("keywords", []))
        overlap = keyword_overlap(brief_keywords, source_keywords)
        artifact_types = source.get("artifact_types", [])
        target_match = 1 if target_profile["profile_id"] in artifact_types else 0

        scores = {
            # --- Content quality & task relevance (wide range, high discrimination) ---
            "task_fit": _bounded_score(0.5 + overlap / 1.5 + target_match * 1.5),
            "objective_coverage": _bounded_score(0.5 + min(overlap, 8) / 1.2),
            "extensibility": _bounded_score(0.8 + min(len(source.get("units", [])), 8) / 3.0),
            "api_coherence": _bounded_score(0.8 + min(len([unit for unit in source.get("units", []) if unit["kind"] in {"class", "function", "export"}]), 6) * 0.6),
            # --- Structural & operational (moderate range) ---
            "structural_clarity": _bounded_score(
                1.0
                + (1.2 if source.get("docs_presence") else 0.0)
                + (0.8 if source.get("manifest_presence") else 0.0)
                + (0.5 if source.get("entrypoints") else 0.0)
            ),
            "maintainability": _bounded_score(
                1.2
                + (1.0 if source.get("docs_presence") else 0.0)
                + (1.0 if source.get("tests_presence") else 0.0)
                + (0.6 if source.get("metadata_quality") == "high" else 0.0)
            ),
            "operator_experience": _bounded_score(1.2 + (1.5 if source.get("docs_presence") else 0.0) + (0.8 if source.get("entrypoints") else 0.0)),
            "compatibility_risk": _bounded_score(3.5 - min(len(source.get("operational_risk_signals", [])), 4) * 0.7),
            "integration_fit": _bounded_score(2.1 + (1.2 if source.get("entrypoints") else 0.0)),
            # --- Compliance & safety (compressed range, lower base) ---
            "testability": _bounded_score(1.0 + (2.0 if source.get("tests_presence") else 0.0) + target_match * 0.5),
            "maintenance_cost": _bounded_score(3.5 - min(source.get("maturity_signals", {}).get("file_count", 0), 40) / 20.0),
            "provenance_safety": _bounded_score(3.0 if source.get("license") != "unknown" else 1.5),
            "dependency_safety": _bounded_score(3.5 - min(source.get("dependency_signals", {}).get("dependency_mentions", 0), 6) * 0.3),
            "dependency_realism": _bounded_score(3.0 - min(source.get("dependency_signals", {}).get("dependency_mentions", 0), 5) * 0.2),
            # --- Profile-specific (unchanged, only active when profile weights include them) ---
            "skill_se_kit_compatibility": _bounded_score(2.5 + (1.5 if "skill" in artifact_types else 0.0)),
            "governor_readiness": _bounded_score(2.0 + (1.5 if source.get("manifest_presence") else 0.0) + (0.8 if source.get("tests_presence") else 0.0)),
            "protocol_compatibility": _bounded_score(2.0 + (1.8 if "protocol" in artifact_types else 0.0)),
            "ambiguity_reduction": _bounded_score(2.2 + (1.0 if source.get("metadata_quality") == "high" else 0.0)),
            "rollout_safety": _bounded_score(2.0 + (1.5 if "feature" in artifact_types else 0.0) + (0.5 if source.get("tests_presence") else 0.0)),
        }

        # Apply fixed score overrides from the brief's scoring_overrides.
        scoring_overrides = brief.get("scoring_overrides") or {}
        for dimension, overrides in scoring_overrides.items():
            if isinstance(overrides, dict) and "score" in overrides:
                scores[dimension] = _bounded_score(float(overrides["score"]))
            elif isinstance(overrides, dict) and dimension not in scores and "weight" in overrides:
                # Custom dimension with a weight but no explicit score — assign neutral baseline.
                scores[dimension] = _bounded_score(2.5)

        strengths: List[str] = []
        if source.get("docs_presence"):
            strengths.append("Has discoverable documentation or narrative guidance.")
        if source.get("tests_presence"):
            strengths.append("Includes tests or validation assets that can be reused.")
        if target_profile["profile_id"] in artifact_types:
            strengths.append(f"Already aligned with the target profile `{target_profile['profile_id']}`.")
        if source.get("metadata_quality") == "high":
            strengths.append("Carries strong metadata, which helps provenance and auditability.")
        if source.get("entrypoints"):
            strengths.append("Exposes entrypoints or integration surfaces clearly.")
        if not strengths:
            strengths.append("Provides at least one reusable structure or workflow unit.")

        weaknesses: List[str] = []
        for risk in source.get("operational_risk_signals", []):
            weaknesses.append(risk.capitalize() + ".")
        if not source.get("tests_presence"):
            weaknesses.append("Validation depth is limited because tests are not obvious.")
        if source.get("artifact_types") == ["generic"]:
            weaknesses.append("Target fit relies on heuristics instead of explicit artifact typing.")
        weaknesses = limited(weaknesses, limit=5)

        reusable_units = [
            {
                "unit_id": unit["unit_id"],
                "name": unit["name"],
                "kind": unit["kind"],
            }
            for unit in source.get("units", [])[:8]
        ]
        risky_units = [
            {
                "name": unit["name"],
                "reason": "low-confidence generic unit" if unit["kind"] == "paragraph" else "needs adaptation",
            }
            for unit in source.get("units", [])
            if unit["kind"] in {"paragraph", "json-key"} and len(unit.get("summary", "")) < 30
        ][:5]

        return {
            "source_id": source["source_id"],
            "target_capability": brief.get("target_job") or brief.get("objective") or "unspecified target capability",
            "scope": compact_excerpt(source.get("content_summary", ""), max_chars=160),
            "core_structure": source.get("file_tree_summary", [])[:12],
            "workflow": _workflow_summary(source),
            "interfaces": source.get("entrypoints", []),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "performance_strengths": [
                "High task overlap with the target brief." if overlap else "Reusable building blocks are present."
            ],
            "failure_modes": _failure_modes(source),
            "maintainability_notes": _maintainability_notes(source),
            "portability_notes": _portability_notes(source),
            "test_maturity": "high" if source.get("tests_presence") else "low",
            "reusable_patterns": reusable_units,
            "non_reusable_or_risky_elements": risky_units,
            "provenance_implications": _provenance_notes(source),
            "scores": scores,
            "keywords": list(source_keywords)[:20],
        }


class ComparisonEngine:
    def build(
        self,
        analysis_reports: Sequence[Dict[str, Any]],
        normalized_sources: Sequence[Dict[str, Any]],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        source_index = {item["source_id"]: item for item in normalized_sources}
        weights = dict(target_profile.get("default_weights", {}))

        # Apply user-specified scoring overrides from the brief.
        scoring_overrides = brief.get("scoring_overrides") or {}
        for dimension, overrides in scoring_overrides.items():
            if isinstance(overrides, dict) and "weight" in overrides:
                weights[dimension] = float(overrides["weight"])

        for criterion in brief.get("success_criteria", []) or []:
            lowered = str(criterion).lower()
            if "test" in lowered:
                weights["testability"] = weights.get("testability", 1.0) + 0.3
            if "compat" in lowered or "protocol" in lowered:
                weights["compatibility_risk"] = weights.get("compatibility_risk", 1.0) + 0.3
            if "maintain" in lowered:
                weights["maintainability"] = weights.get("maintainability", 1.0) + 0.3

        hard_gates = self._constraint_gates(normalized_sources, brief=brief, target_profile=target_profile)
        scored_sources: List[Dict[str, Any]] = []
        for report in analysis_reports:
            gate = hard_gates[report["source_id"]]
            weighted_total = 0.0
            weight_sum = 0.0
            for dimension, score in report["scores"].items():
                if dimension not in weights:
                    continue
                weighted_total += score * weights[dimension]
                weight_sum += weights[dimension]
            overall = round(weighted_total / weight_sum, 3) if weight_sum else 0.0
            scored_sources.append(
                {
                    "source_id": report["source_id"],
                    "overall_score": overall,
                    "status": "pass" if gate["passed"] else "fail",
                    "scores": {dimension: round(report["scores"].get(dimension, 0.0), 3) for dimension in weights},
                    "rationales": {
                        "strengths": report["strengths"][:3],
                        "weaknesses": report["weaknesses"][:3],
                    },
                }
            )
        scored_sources.sort(key=lambda item: (-item["overall_score"], item["source_id"]))
        complementarity = self._pairings(scored_sources, analysis_reports, source_index)
        matrix_markdown = self._matrix_markdown(scored_sources, weights)
        return {
            "weights": weights,
            "source_rankings": scored_sources,
            "constraint_gates": list(hard_gates.values()),
            "complementarity": complementarity,
            "comparison_matrix_markdown": matrix_markdown,
        }

    def _constraint_gates(
        self,
        normalized_sources: Sequence[Dict[str, Any]],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        forbidden_licenses = {item.lower() for item in brief.get("forbidden_licenses", [])}
        required_artifact_types = set(brief.get("required_artifact_types", []))
        gate_map: Dict[str, Dict[str, Any]] = {}
        for source in normalized_sources:
            reasons: List[str] = []
            license_name = str(source.get("license", "unknown")).lower()
            if forbidden_licenses and license_name in forbidden_licenses:
                reasons.append(f"license `{source.get('license')}` is forbidden")
            if required_artifact_types and not (required_artifact_types & set(source.get("artifact_types", []))):
                reasons.append("required artifact type is missing")
            if brief.get("require_tests") and not source.get("tests_presence"):
                reasons.append("tests are required by the brief")
            if brief.get("must_match_target_profile") and target_profile["profile_id"] not in source.get("artifact_types", []):
                reasons.append("source does not natively match the target profile")
            gate_map[source["source_id"]] = {
                "source_id": source["source_id"],
                "passed": not reasons,
                "reasons": reasons or ["passed all hard gates"],
            }
        return gate_map

    def _pairings(
        self,
        scored_sources: Sequence[Dict[str, Any]],
        analysis_reports: Sequence[Dict[str, Any]],
        source_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        report_index = {item["source_id"]: item for item in analysis_reports}
        pairings: List[Dict[str, Any]] = []
        for left_index, left in enumerate(scored_sources):
            for right in scored_sources[left_index + 1 :]:
                left_source = source_index[left["source_id"]]
                right_source = source_index[right["source_id"]]
                diversity = len(set(left_source.get("artifact_types", [])) ^ set(right_source.get("artifact_types", [])))
                strength_mix = len(set(report_index[left["source_id"]]["strengths"]) ^ set(report_index[right["source_id"]]["strengths"]))
                pairings.append(
                    {
                        "pair": [left["source_id"], right["source_id"]],
                        "complementarity_score": round(min(5.0, 1.0 + diversity + strength_mix / 3.0), 3),
                        "reason": "The pair offers complementary artifact coverage and distinct strengths.",
                    }
                )
        pairings.sort(key=lambda item: (-item["complementarity_score"], item["pair"]))
        return pairings[:5]

    def _matrix_markdown(self, scored_sources: Sequence[Dict[str, Any]], weights: Dict[str, float]) -> str:
        dimensions = list(weights.keys())
        header = "| Source | Status | Overall | " + " | ".join(dimensions) + " |"
        divider = "| --- | --- | --- | " + " | ".join("---" for _ in dimensions) + " |"
        rows = [header, divider]
        for source in scored_sources:
            scores = [f"{source['scores'].get(dimension, 0.0):.2f}" for dimension in dimensions]
            rows.append(
                f"| {source['source_id']} | {source['status']} | {source['overall_score']:.2f} | "
                + " | ".join(scores)
                + " |"
            )
        return "\n".join(rows) + "\n"


class StrategySynthesizer:
    # Keywords in the brief that signal multi-source synthesis intent.
    _MULTI_SOURCE_KEYWORDS = frozenset({
        "combine", "combining", "synthesize", "synthesizing",
        "merge", "merging", "fuse", "fusing",
        "integrate", "integrating", "blend", "blending",
        "mix", "mixing", "union", "unify",
    })

    def synthesize(
        self,
        comparison: Dict[str, Any],
        analysis_reports: Sequence[Dict[str, Any]],
        normalized_sources: Sequence[Dict[str, Any]],
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        rankings = comparison["source_rankings"]
        analysis_index = {report["source_id"]: report for report in analysis_reports}
        top_sources = [item for item in rankings if item["status"] == "pass"] or rankings
        lead = top_sources[0]
        pair = comparison["complementarity"][0] if comparison["complementarity"] else None
        strategy_base = slugify(target_profile["profile_id"])
        options: List[Dict[str, Any]] = []

        options.append(
            self._build_strategy(
                strategy_id=f"{strategy_base}-conservative-harden",
                name="Conservative Harden",
                source_ids=[lead["source_id"]],
                analysis_index=analysis_index,
                preserve_prefix="Preserve the strongest existing structures and harden the weak edges.",
                introduce=[
                    "Add explicit provenance mapping.",
                    "Add profile-specific verification and release metadata.",
                ],
                brief=brief,
                target_profile=target_profile,
                score=lead["overall_score"],
            )
        )

        if pair:
            pair_score = next(item["overall_score"] for item in rankings if item["source_id"] == pair["pair"][1])
            options.append(
                self._build_strategy(
                    strategy_id=f"{strategy_base}-balanced-synthesis",
                    name="Balanced Synthesis",
                    source_ids=pair["pair"],
                    analysis_index=analysis_index,
                    preserve_prefix="Combine the clearest backbone with complementary strengths from a second source.",
                    introduce=[
                        "Fuse the two most complementary source patterns.",
                        "Retain explicit migration guidance for cross-source differences.",
                    ],
                    brief=brief,
                    target_profile=target_profile,
                    score=round((lead["overall_score"] + pair_score + pair["complementarity_score"]) / 3.0, 3),
                )
            )

        options.append(
            self._build_strategy(
                strategy_id=f"{strategy_base}-forward-port",
                name="Forward Port",
                source_ids=[item["source_id"] for item in top_sources[:2]],
                analysis_index=analysis_index,
                preserve_prefix="Use the best current source as the base, then port it toward the new target profile or runtime.",
                introduce=[
                    f"Explicitly optimize for target profile `{target_profile['profile_id']}`.",
                    "Add modern packaging and handoff scaffolding even when the source material lacks it.",
                ],
                brief=brief,
                target_profile=target_profile,
                score=round(lead["overall_score"] - 0.1, 3),
            )
        )

        # Boost multi-source strategies when the brief signals synthesis intent.
        if self._has_multi_source_intent(brief):
            for option in options:
                if option["name"] in {"Balanced Synthesis", "Forward Port"}:
                    option["strategy_score"] = round(option["strategy_score"] + 0.5, 3)
                elif option["name"] == "Conservative Harden":
                    option["strategy_score"] = round(option["strategy_score"] - 0.3, 3)
            options.sort(key=lambda item: (-item["strategy_score"], item["strategy_id"]))

        return limited(options, limit=3)

    @classmethod
    def _has_multi_source_intent(cls, brief: Dict[str, Any]) -> bool:
        """Return True if the brief's text fields contain multi-source intent keywords."""
        text = " ".join(
            str(brief.get(field) or "")
            for field in ("target_job", "objective", "description")
        ).lower()
        return bool(cls._MULTI_SOURCE_KEYWORDS & set(text.split()))

    def _build_strategy(
        self,
        *,
        strategy_id: str,
        name: str,
        source_ids: Sequence[str],
        analysis_index: Dict[str, Dict[str, Any]],
        preserve_prefix: str,
        introduce: Sequence[str],
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        score: float,
    ) -> Dict[str, Any]:
        preserve = [preserve_prefix]
        discard: List[str] = []
        adapt: List[str] = []
        risks: List[str] = []
        for source_id in source_ids:
            report = analysis_index[source_id]
            preserve.extend(report["strengths"][:2])
            discard.extend(report["weaknesses"][:2])
            adapt.extend(f"Adapt {pattern['name']} from {source_id}" for pattern in report["reusable_patterns"][:2])
            risks.extend(report["failure_modes"][:2])

        expected_shape = [target_profile["artifact_type"], target_profile.get("packaging_profile", "default bundle")]
        verification_burden = "high" if len(source_ids) > 1 else "medium"
        migration_burden = "medium" if brief.get("transformation_mode") in {"port", "replace"} else "low"
        return {
            "strategy_id": strategy_id,
            "name": name,
            "source_ids": list(source_ids),
            "preserve": limited(preserve, limit=5),
            "discard": limited(list(dict.fromkeys(discard)), limit=5),
            "adapt": limited(list(dict.fromkeys(adapt)), limit=5),
            "introduce": list(introduce),
            "why_it_serves_the_brief": f"Targets `{target_profile['profile_id']}` while serving `{brief.get('target_job', 'the requested job')}`.",
            "tradeoffs": [
                "Higher inspectability than a free-form merge.",
                "More upfront packaging work in exchange for clearer handoff.",
            ],
            "risks": limited(list(dict.fromkeys(risks)), limit=5),
            "expected_output_shape": expected_shape,
            "expected_verification_burden": verification_burden,
            "expected_migration_burden": migration_burden,
            "strategy_score": round(score, 3),
        }


class BuildPlanner:
    def create_plan(
        self,
        *,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
    ) -> Dict[str, Any]:
        deliverables = self._deliverables_for_profile(target_profile)
        return {
            "target_profile": target_profile["profile_id"],
            "packaging_profile": target_profile["packaging_profile"],
            "strategy_id": selected_strategy["strategy_id"],
            "target_artifact_topology": selected_strategy["expected_output_shape"],
            "deliverables": deliverables,
            "interface_plan": self._interface_plan(target_profile, brief),
            "build_steps": self._build_steps(target_profile, brief),
            "companion_skill_wrapper_needed": bool(
                brief.get("governor_ready")
                and target_profile["profile_id"] != "skill"
            ),
            "audit_requirements": [
                "summary",
                "comparison evidence",
                "risk register",
                "provenance map",
            ],
            "verification_plan": target_profile.get("verification_focus", []),
            "migration_plan": [
                "Document preserved source ideas.",
                "Document rejected or adapted source ideas.",
                "Attach authority-specific handoff metadata.",
            ],
            "handoff_plan": self._handoff_plan(target_profile, brief),
        }

    def _deliverables_for_profile(self, target_profile: Dict[str, Any]) -> List[str]:
        if target_profile["profile_id"] == "compound":
            deliverables = ["artifact_manifest.json", "provenance.json"]
            for child in target_profile.get("child_profiles", []):
                deliverables.extend(self._deliverables_for_profile(child))
            return deliverables
        return list(target_profile.get("required_outputs", []))

    def _interface_plan(self, target_profile: Dict[str, Any], brief: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "target_runtime": brief.get("target_runtime", "local"),
            "declared_interfaces": brief.get("declared_interfaces", []),
            "compatibility_constraints": brief.get("compatibility_constraints", []),
        }

    def _build_steps(self, target_profile: Dict[str, Any], brief: Dict[str, Any]) -> List[str]:
        common_steps = [
            "Materialize selected strategy into a profile-specific bundle.",
            "Generate provenance, audit, and release metadata.",
            "Run shared and profile-specific verification checks.",
        ]
        if target_profile["profile_id"] == "skill":
            common_steps.insert(0, "Generate protocol-compatible skill manifest and SKILL.md.")
        elif target_profile["profile_id"] == "protocol":
            common_steps.insert(0, "Generate schema bundle, examples, and compatibility notes.")
        elif target_profile["profile_id"] == "module":
            common_steps.insert(0, "Generate package layout, source entrypoints, and tests.")
        elif target_profile["profile_id"] == "feature":
            common_steps.insert(0, "Generate spec, acceptance criteria, rollout, and instrumentation plans.")
        elif target_profile["profile_id"] == "product":
            common_steps.insert(0, "Generate PRD, roadmap, and dependency maps.")
        elif target_profile["profile_id"] == "compound":
            common_steps.insert(0, "Generate a coordinated bundle across child profiles.")
        if brief.get("governor_ready"):
            common_steps.append("Generate governor-ready handoff metadata.")
        return common_steps

    def _handoff_plan(self, target_profile: Dict[str, Any], brief: Dict[str, Any]) -> Dict[str, Any]:
        if target_profile["profile_id"] == "skill":
            authority = "governor" if brief.get("governor_ready") else "local operator"
        else:
            authority = brief.get("native_authority", "native owner")
        return {
            "authority": authority,
            "governor_ready": bool(brief.get("governor_ready")),
            "release_modes": [
                "local preview",
                "review bundle",
                "release bundle",
            ],
        }


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(5.0, value)), 3)


def _stringify_brief_values(brief: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for value in brief.values():
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        elif isinstance(value, dict):
            values.extend(str(item) for item in value.values())
        else:
            values.append(str(value))
    return values


def _workflow_summary(source: Dict[str, Any]) -> List[str]:
    units = source.get("units", [])
    return [unit["name"] for unit in units[:4]] or ["implicit workflow"]


def _failure_modes(source: Dict[str, Any]) -> List[str]:
    risks = list(source.get("operational_risk_signals", []))
    if not risks:
        risks.append("Porting assumptions may not hold in the target environment.")
    return limited(risks, limit=4)


def _maintainability_notes(source: Dict[str, Any]) -> List[str]:
    notes = []
    if source.get("docs_presence"):
        notes.append("Documentation lowers maintenance overhead.")
    if source.get("tests_presence"):
        notes.append("Tests create safer iteration paths.")
    if source.get("metadata_quality") == "low":
        notes.append("Sparse metadata will slow future review work.")
    return notes or ["Maintainability depends on reconstructing missing context."]


def _portability_notes(source: Dict[str, Any]) -> List[str]:
    if "protocol" in source.get("artifact_types", []):
        return ["Protocol-oriented structure should port well across runtimes."]
    if "module" in source.get("artifact_types", []):
        return ["Module packaging suggests a portable core if dependencies are controlled."]
    return ["Portability is plausible but will require profile-specific adaptation."]


def _provenance_notes(source: Dict[str, Any]) -> List[str]:
    notes = [f"License: {source.get('license', 'unknown')}."]
    if source.get("metadata_quality") == "high":
        notes.append("Metadata quality supports auditability.")
    else:
        notes.append("Metadata gaps require reviewer attention.")
    return notes
