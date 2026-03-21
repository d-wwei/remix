from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from skill_se_kit.common import dump_json, generate_id, utc_now_iso
from remix.builder import AuditComposer, ReleaseManager, TargetBuilder
from remix.planning import BuildPlanner, ComparisonEngine, SourceAnalyzer, StrategySynthesizer
from remix.profiles import TargetProfileRegistry
from remix.sources import SourceAdapter
from remix.verification import VerificationOrchestrator
from remix.workspace import RemixRunWorkspace
from skill_se_kit.runtime.skill_runtime import SkillRuntime


class RemixRuntime:
    def __init__(self, *, skill_root: str | Path, protocol_root: str | Path):
        self.skill_runtime = SkillRuntime(skill_root=skill_root, protocol_root=protocol_root)
        self.profile_registry = TargetProfileRegistry()
        self.source_adapter = SourceAdapter()
        self.source_analyzer = SourceAnalyzer()
        self.comparison_engine = ComparisonEngine()
        self.strategy_synthesizer = StrategySynthesizer()
        self.build_planner = BuildPlanner()
        self.target_builder = TargetBuilder(self.skill_runtime.protocol_adapter)
        self.verifier = VerificationOrchestrator(self.skill_runtime.protocol_adapter)
        self.audit_composer = AuditComposer()
        self.release_manager = ReleaseManager()

    @property
    def workspace(self):
        return self.skill_runtime.workspace

    def bootstrap(self, manifest: Dict[str, Any]) -> None:
        self.skill_runtime.workspace.bootstrap(manifest)

    def detect_governor(self) -> bool:
        return self.skill_runtime.detect_governor()

    def list_profiles(self) -> List[Dict[str, Any]]:
        return self.profile_registry.list_profiles()

    def run(
        self,
        *,
        brief: Dict[str, Any],
        sources: Sequence[Dict[str, Any]],
        selected_strategy_id: str | None = None,
        run_id: str | None = None,
        run_root: str | Path | None = None,
    ) -> Dict[str, Any]:
        target_profile = self.profile_registry.resolve(brief)
        run_id = run_id or generate_id("remix-run")
        workspace = RemixRunWorkspace(run_root or self._default_run_root(run_id))
        workspace.ensure_layout()

        workspace.write_json(workspace.brief_path, dict(brief))
        workspace.write_json(workspace.target_profile_path, target_profile)
        workspace.write_json(workspace.source_catalog_path, {"sources": list(sources)})
        workspace.write_json(workspace.expanded_candidates_path, {"sources": []})

        normalized_sources = self.source_adapter.normalize_sources(sources, brief)
        for source in normalized_sources:
            workspace.write_json(workspace.normalized_sources_dir / f"{source['source_id']}.json", source)

        analysis_reports = self.source_analyzer.analyze_sources(
            normalized_sources,
            brief=brief,
            target_profile=target_profile,
        )
        for report in analysis_reports:
            workspace.write_json(workspace.analysis_reports_dir / f"{report['source_id']}.json", report)

        comparison = self.comparison_engine.build(
            analysis_reports,
            normalized_sources,
            brief=brief,
            target_profile=target_profile,
        )
        workspace.write_text(workspace.comparison_matrix_path, comparison["comparison_matrix_markdown"])
        workspace.write_json(
            workspace.comparison_scores_path,
            {
                "weights": comparison["weights"],
                "source_rankings": comparison["source_rankings"],
                "complementarity": comparison["complementarity"],
            },
        )
        workspace.write_json(workspace.constraint_gates_path, {"gates": comparison["constraint_gates"]})

        strategies = self.strategy_synthesizer.synthesize(
            comparison,
            analysis_reports,
            normalized_sources,
            brief=brief,
            target_profile=target_profile,
        )
        workspace.write_json(workspace.strategy_options_path, {"strategies": strategies})
        selected_strategy = self._select_strategy(strategies, selected_strategy_id=selected_strategy_id)
        workspace.write_json(workspace.selected_strategy_path, selected_strategy)
        workspace.write_json(
            workspace.decision_log_path,
            {
                "run_id": run_id,
                "selected_strategy_id": selected_strategy["strategy_id"],
                "selected_at": utc_now_iso(),
                "selection_mode": "explicit" if selected_strategy_id else "auto",
            },
        )

        build_plan = self.build_planner.create_plan(
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
        )
        workspace.write_json(workspace.build_plan_path, build_plan)

        build_result = self.target_builder.build(
            workspace=workspace,
            brief=brief,
            target_profile=target_profile,
            build_plan=build_plan,
            selected_strategy=selected_strategy,
            normalized_sources=normalized_sources,
            analysis_reports=analysis_reports,
        )
        verification = self.verifier.verify(
            workspace=workspace,
            brief=brief,
            target_profile=target_profile,
            build_plan=build_plan,
            selected_strategy=selected_strategy,
            normalized_sources=normalized_sources,
            build_result=build_result,
        )
        self.audit_composer.compose(
            workspace=workspace,
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
            normalized_sources=normalized_sources,
            comparison=comparison,
            verification=verification,
        )
        self.release_manager.compose_handoff(
            workspace=workspace,
            brief=brief,
            target_profile=target_profile,
            build_plan=build_plan,
            verification=verification,
        )

        self._record_run_experience(
            run_id=run_id,
            brief=brief,
            target_profile=target_profile,
            selected_strategy=selected_strategy,
            verification=verification,
            workspace=workspace,
        )

        summary = {
            "run_id": run_id,
            "run_root": str(workspace.root),
            "target_profile": target_profile["profile_id"],
            "packaging_profile": target_profile.get("packaging_profile"),
            "selected_strategy_id": selected_strategy["strategy_id"],
            "overall_status": verification["overall_status"],
            "generated_outputs": build_result["outputs"],
            "comparison_top_source": comparison["source_rankings"][0]["source_id"] if comparison["source_rankings"] else None,
        }
        dump_json(workspace.release_bundle_dir / "run_summary.json", summary)
        return summary

    def _default_run_root(self, run_id: str) -> Path:
        return self.workspace.metadata_root / "remix" / "runs" / run_id

    def _select_strategy(self, strategies: Sequence[Dict[str, Any]], *, selected_strategy_id: str | None) -> Dict[str, Any]:
        if not strategies:
            raise ValueError("No strategy options were synthesized")
        if selected_strategy_id:
            for strategy in strategies:
                if strategy["strategy_id"] == selected_strategy_id:
                    return strategy
            raise ValueError(f"Unknown strategy id: {selected_strategy_id}")
        return max(strategies, key=lambda item: item.get("strategy_score", 0.0))

    def _record_run_experience(
        self,
        *,
        run_id: str,
        brief: Dict[str, Any],
        target_profile: Dict[str, Any],
        selected_strategy: Dict[str, Any],
        verification: Dict[str, Any],
        workspace: RemixRunWorkspace,
    ) -> None:
        self.skill_runtime.record_experience(
            kind="observation",
            summary=f"remix run {run_id} finished with {verification['overall_status']}",
            source_origin="remix",
            outcome={
                "status": "positive" if verification["overall_status"] == "pass" else "mixed",
                "impact": "high",
            },
            metadata={
                "run_id": run_id,
                "target_profile": target_profile["profile_id"],
                "selected_strategy_id": selected_strategy["strategy_id"],
                "verification": verification["summary"],
                "run_root": str(workspace.root),
                "target_job": brief.get("target_job"),
            },
        )


# Backward-compatible alias during the repo split transition.
RemixSkillRuntime = RemixRuntime
