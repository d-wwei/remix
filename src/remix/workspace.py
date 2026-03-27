from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from remix.utils import dump_json, write_text


class RemixRunWorkspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    @property
    def brief_path(self) -> Path:
        return self.root / "remix_brief.json"

    @property
    def target_profile_path(self) -> Path:
        return self.root / "target_profile.json"

    @property
    def source_catalog_path(self) -> Path:
        return self.root / "source_catalog.json"

    @property
    def expanded_candidates_path(self) -> Path:
        return self.root / "expanded_candidates.json"

    @property
    def normalized_sources_dir(self) -> Path:
        return self.root / "normalized_sources"

    @property
    def analysis_reports_dir(self) -> Path:
        return self.root / "analysis_reports"

    @property
    def comparison_matrix_path(self) -> Path:
        return self.root / "comparison_matrix.md"

    @property
    def comparison_scores_path(self) -> Path:
        return self.root / "comparison_scores.json"

    @property
    def constraint_gates_path(self) -> Path:
        return self.root / "constraint_gates.json"

    @property
    def strategy_options_path(self) -> Path:
        return self.root / "strategy_options.json"

    @property
    def selected_strategy_path(self) -> Path:
        return self.root / "selected_strategy.json"

    @property
    def decision_log_path(self) -> Path:
        return self.root / "decision_log.json"

    @property
    def build_plan_path(self) -> Path:
        return self.root / "build_plan.json"

    @property
    def source_influence_map_path(self) -> Path:
        return self.root / "source_influence_map.json"

    @property
    def remixed_output_dir(self) -> Path:
        return self.root / "remixed_output"

    @property
    def artifact_manifest_path(self) -> Path:
        return self.remixed_output_dir / "artifact_manifest.json"

    @property
    def provenance_path(self) -> Path:
        return self.remixed_output_dir / "provenance.json"

    @property
    def audit_dir(self) -> Path:
        return self.root / "audit"

    @property
    def audit_summary_path(self) -> Path:
        return self.audit_dir / "audit_summary.md"

    @property
    def source_table_path(self) -> Path:
        return self.audit_dir / "source_table.md"

    @property
    def audit_decision_log_path(self) -> Path:
        return self.audit_dir / "decision_log.json"

    @property
    def risk_register_path(self) -> Path:
        return self.audit_dir / "risk_register.md"

    @property
    def evidence_index_path(self) -> Path:
        return self.audit_dir / "evidence_index.json"

    @property
    def verification_report_path(self) -> Path:
        return self.root / "verification_report.md"

    @property
    def verification_results_path(self) -> Path:
        return self.root / "verification_results.json"

    @property
    def handoff_report_path(self) -> Path:
        return self.root / "handoff_report.md"

    @property
    def release_bundle_dir(self) -> Path:
        return self.root / "release_bundle"

    def ensure_layout(self) -> None:
        for directory in [
            self.root,
            self.normalized_sources_dir,
            self.analysis_reports_dir,
            self.remixed_output_dir / "skill",
            self.remixed_output_dir / "protocol" / "schemas",
            self.remixed_output_dir / "protocol" / "examples",
            self.remixed_output_dir / "module" / "src",
            self.remixed_output_dir / "module" / "tests",
            self.remixed_output_dir / "feature",
            self.remixed_output_dir / "product",
            self.remixed_output_dir / "docs",
            self.remixed_output_dir / "tests",
            self.audit_dir,
            self.release_bundle_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        dump_json(path, payload)

    def write_text(self, path: Path, content: str) -> None:
        write_text(path, content)
