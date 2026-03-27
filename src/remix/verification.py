from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from jsonschema import Draft202012Validator


class VerificationOrchestrator:
    def __init__(self, validator) -> None:
        self.validator = validator

    def verify(
        self,
        *,
        workspace,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        build_plan: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        normalized_sources: Sequence[Dict[str, Any]],
        build_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        output_paths = [item["path"] for item in build_result["outputs"]]
        known_sources = {source["source_id"] for source in normalized_sources}

        for deliverable in build_plan["deliverables"]:
            checks.append(self._file_exists_check(workspace, deliverable))

        checks.append(
            {
                "name": "strategy-alignment",
                "status": "pass" if selected_strategy["preserve"] and build_result["outputs"] else "fail",
                "details": "The generated bundle includes outputs and preserved ideas.",
            }
        )

        influence_outputs = build_result["source_influence_map"]["outputs"]
        checks.append(
            {
                "name": "source-attribution-sanity",
                "status": "pass"
                if all(item["source_id"] in known_sources for item in influence_outputs)
                else "fail",
                "details": "Every output influence references a known source id.",
            }
        )

        checks.append(
            {
                "name": "provenance-completeness",
                "status": "pass" if len(influence_outputs) >= len(build_result["outputs"]) else "warn",
                "details": "Each output should have at least one provenance mapping.",
            }
        )

        checks.extend(self._profile_specific_checks(workspace, target_profile=target_profile, brief=brief))

        passed = sum(1 for item in checks if item["status"] == "pass")
        warnings = sum(1 for item in checks if item["status"] == "warn")
        failed = sum(1 for item in checks if item["status"] == "fail")
        overall_status = "fail" if failed else "warn" if warnings else "pass"

        results = {
            "overall_status": overall_status,
            "summary": {"passed": passed, "warnings": warnings, "failed": failed},
            "checks": checks,
            "generated_outputs": output_paths,
        }
        workspace.write_json(workspace.verification_results_path, results)
        workspace.write_text(workspace.verification_report_path, self._report_markdown(results))
        return results

    def _file_exists_check(self, workspace, relative_path: str) -> Dict[str, Any]:
        path = workspace.remixed_output_dir / relative_path
        return {
            "name": f"deliverable:{relative_path}",
            "status": "pass" if path.exists() else "fail",
            "details": f"Expected deliverable `{relative_path}` exists.",
        }

    def _profile_specific_checks(self, workspace, *, target_profile: Dict[str, Any], brief: Dict[str, Any]) -> List[Dict[str, Any]]:
        profile_id = target_profile["profile_id"]
        if profile_id == "compound":
            checks: List[Dict[str, Any]] = []
            for child in target_profile.get("child_profiles", []):
                checks.extend(self._profile_specific_checks(workspace, target_profile=child, brief=brief))
            return checks
        if profile_id == "skill":
            return self._verify_skill(workspace, brief=brief)
        if profile_id == "protocol":
            return self._verify_protocol(workspace)
        if profile_id == "module":
            return self._verify_module(workspace, packaging_profile=target_profile.get("packaging_profile"))
        if profile_id == "feature":
            return self._verify_feature(workspace)
        if profile_id == "product":
            return self._verify_product(workspace)
        return []

    def _verify_skill(self, workspace, *, brief: Dict[str, Any]) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        manifest_path = workspace.remixed_output_dir / "skill" / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.validator.validate_manifest(manifest)
            checks.append({"name": "skill-manifest-validation", "status": "pass", "details": "Generated skill manifest is protocol-compatible."})
        except Exception as exc:  # pragma: no cover - exercised in failure scenarios
            checks.append({"name": "skill-manifest-validation", "status": "fail", "details": str(exc)})

        if brief.get("governor_ready"):
            proposal_path = workspace.release_bundle_dir / "governor_candidate" / "skill_proposal.json"
            try:
                proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                self.validator.validate_proposal(proposal)
                checks.append({"name": "governor-candidate-validation", "status": "pass", "details": "Governor-ready candidate proposal validates."})
            except Exception as exc:  # pragma: no cover - exercised in failure scenarios
                checks.append({"name": "governor-candidate-validation", "status": "fail", "details": str(exc)})
        return checks

    def _verify_protocol(self, workspace) -> List[Dict[str, Any]]:
        schema_path = workspace.remixed_output_dir / "protocol" / "schemas" / "remixed.schema.json"
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            return [{"name": "protocol-schema-validation", "status": "pass", "details": "Generated protocol schema is valid draft-2020-12 JSON Schema."}]
        except Exception as exc:  # pragma: no cover - exercised in failure scenarios
            return [{"name": "protocol-schema-validation", "status": "fail", "details": str(exc)}]

    def _verify_module(self, workspace, *, packaging_profile: str | None) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        if packaging_profile == "npm-package":
            package_json = workspace.remixed_output_dir / "module" / "package.json"
            checks.append(
                {
                    "name": "module-package-json",
                    "status": "pass" if package_json.exists() else "fail",
                    "details": "NPM package metadata exists.",
                }
            )
        else:
            pyproject = workspace.remixed_output_dir / "module" / "pyproject.toml"
            checks.append(
                {
                    "name": "module-pyproject",
                    "status": "pass" if pyproject.exists() else "fail",
                    "details": "Python package metadata exists.",
                }
            )
            source_files = list((workspace.remixed_output_dir / "module" / "src").rglob("*.py"))
            checks.append(
                {
                    "name": "module-source-files",
                    "status": "pass" if source_files else "fail",
                    "details": "Python source entrypoints are present.",
                }
            )
        return checks

    def _verify_feature(self, workspace) -> List[Dict[str, Any]]:
        checks = []
        spec = workspace.remixed_output_dir / "feature" / "spec.md"
        rollout = workspace.remixed_output_dir / "feature" / "rollout_plan.md"
        for name, path in [("feature-spec", spec), ("feature-rollout", rollout)]:
            checks.append(
                {
                    "name": name,
                    "status": "pass" if path.exists() and "##" in path.read_text(encoding="utf-8") else "fail",
                    "details": f"{path.name} exists and contains structured sections.",
                }
            )
        return checks

    def _verify_product(self, workspace) -> List[Dict[str, Any]]:
        prd = workspace.remixed_output_dir / "product" / "PRD.md"
        roadmap = workspace.remixed_output_dir / "product" / "roadmap.md"
        checks = []
        for name, path in [("product-prd", prd), ("product-roadmap", roadmap)]:
            checks.append(
                {
                    "name": name,
                    "status": "pass" if path.exists() and path.read_text(encoding="utf-8").strip() else "fail",
                    "details": f"{path.name} exists and is non-empty.",
                }
            )
        return checks

    def _report_markdown(self, results: Dict[str, Any]) -> str:
        lines = [
            "# Verification Report",
            "",
            f"Overall status: {results['overall_status']}",
            "",
            "| Check | Status | Details |",
            "| --- | --- | --- |",
        ]
        for check in results["checks"]:
            lines.append(f"| {check['name']} | {check['status']} | {check['details']} |")
        return "\n".join(lines)
