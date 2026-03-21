from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from skill_se_kit.common import SUPPORTED_PROTOCOL_VERSION, generate_id, utc_now_iso
from remix.utils import compact_excerpt, markdown_bullets, skillify, slugify


class TargetBuilder:
    def __init__(self, protocol_adapter) -> None:
        self.protocol_adapter = protocol_adapter

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
        self.protocol_adapter.validate_manifest(manifest)
        workspace.write_json(workspace.remixed_output_dir / "skill" / "manifest.json", manifest)

        workflows = []
        for source_id in selected_strategy["source_ids"]:
            workflows.extend(analysis_index[source_id]["workflow"][:2])
        skill_md = "\n".join(
            [
                f"# {name}",
                "",
                "## Purpose",
                brief.get("target_job", "Deliver the requested skill outcome."),
                "",
                "## Sources",
                markdown_bullets(selected_strategy["source_ids"]),
                "",
                "## Workflow",
                markdown_bullets(list(dict.fromkeys(workflows))[:6]),
                "",
                "## Constraints",
                markdown_bullets(_brief_constraints(brief)),
                "",
                "## Verification",
                markdown_bullets(
                    [
                        "Protocol-compatible manifest validation",
                        "Scenario smoke checks",
                        "Source attribution sanity checks",
                    ]
                ),
                "",
                "## Provenance",
                "See `../provenance.json` and `../docs/strategy.md` for source influence details.",
                "",
                "## Handoff",
                "This package is ready for local review and optional governed submission through the release bundle.",
            ]
        )
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
                markdown_bullets(
                    [
                        "Launch behind a flag or staged availability mechanism.",
                        "Collect baseline metrics before rollout.",
                        "Prepare rollback triggers and ownership contacts.",
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
        self.protocol_adapter.validate_proposal(proposal)
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
