"""Standalone tests for all six target profiles + scoring_overrides."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.test_support import SRC
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remix.runtime import RemixRuntime


def _output_paths(summary: dict) -> list[str]:
    """Extract output path strings from the summary."""
    return [o["path"] for o in summary["generated_outputs"]]


class ProfileTestBase(unittest.TestCase):
    """Shared helpers for profile tests."""

    def _run(self, *, brief: dict, sources: list | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RemixRuntime(output_root=tmpdir)
            sources = sources or [
                {
                    "kind": "raw_text",
                    "name": "test-source",
                    "content": (
                        "# Source Material\n\n"
                        "## Overview\nA comprehensive guide covering design, testing, and rollout.\n\n"
                        "## API\n- execute(data) -> result\n- validate(input) -> bool\n\n"
                        "## Tests\nUnit tests included.\n\n"
                        "## Roadmap\nPhase 1: MVP. Phase 2: Scale.\n\n"
                        "## Acceptance Criteria\n- Must pass smoke tests\n- Must meet rollout safety bar\n\n"
                        "## Instrumentation\n- Metrics: latency, error rate\n\n"
                        "## Schema\n```json\n{\"$schema\": \"draft-2020-12\"}\n```\n"
                    ),
                },
            ]
            summary = runtime.run(brief=brief, sources=sources)
            summary["_run_root"] = Path(summary["run_root"])
        return summary


class SkillProfileTest(ProfileTestBase):
    def test_skill_profile_pass(self) -> None:
        summary = self._run(
            brief={
                "name": "Test Skill",
                "target_job": "Build a test skill.",
                "target_profile": "skill",
                "governor_ready": False,
                "declared_interfaces": ["skill.execute"],
            },
        )
        self.assertEqual(summary["target_profile"], "skill")
        self.assertEqual(summary["overall_status"], "pass")
        self.assertIn("skill/manifest.json", _output_paths(summary))

    def test_skill_governor_ready(self) -> None:
        summary = self._run(
            brief={
                "name": "Governed Skill",
                "target_job": "Create a governed skill.",
                "target_profile": "skill",
                "governor_ready": True,
                "declared_interfaces": ["skill.execute"],
            },
        )
        self.assertEqual(summary["overall_status"], "pass")
        # Governor candidate is written to release_bundle, not in generated_outputs.
        # Check that skill outputs are present.
        self.assertIn("skill/manifest.json", _output_paths(summary))
        self.assertIn("skill/SKILL.md", _output_paths(summary))


class ProtocolProfileTest(ProfileTestBase):
    def test_protocol_profile_pass(self) -> None:
        summary = self._run(
            brief={
                "name": "Test Protocol",
                "target_job": "Define a protocol for inter-service communication.",
                "target_profile": "protocol",
                "governor_ready": False,
            },
        )
        self.assertEqual(summary["target_profile"], "protocol")
        self.assertEqual(summary["overall_status"], "pass")
        paths = _output_paths(summary)
        self.assertTrue(any("schema" in p for p in paths))


class ModuleProfileTest(ProfileTestBase):
    def test_module_profile_pass(self) -> None:
        summary = self._run(
            brief={
                "name": "Test Module",
                "target_job": "Produce a reusable Python module.",
                "target_profile": "module",
                "packaging_profile": "python-package",
                "governor_ready": False,
                "declared_interfaces": ["module.run"],
            },
        )
        self.assertEqual(summary["target_profile"], "module")
        self.assertEqual(summary["overall_status"], "pass")
        paths = _output_paths(summary)
        self.assertTrue(any("module" in p for p in paths))


class FeatureProfileTest(ProfileTestBase):
    def test_feature_profile_pass(self) -> None:
        summary = self._run(
            brief={
                "name": "Test Feature",
                "target_job": "Design a feature rollout plan.",
                "target_profile": "feature",
                "governor_ready": False,
            },
        )
        self.assertEqual(summary["target_profile"], "feature")
        self.assertEqual(summary["overall_status"], "pass")
        paths = _output_paths(summary)
        self.assertIn("feature/spec.md", paths)
        self.assertIn("feature/rollout_plan.md", paths)


class ProductProfileTest(ProfileTestBase):
    def test_product_profile_pass(self) -> None:
        summary = self._run(
            brief={
                "name": "Test Product",
                "target_job": "Write a product requirements document.",
                "target_profile": "product",
                "governor_ready": False,
            },
        )
        self.assertEqual(summary["target_profile"], "product")
        self.assertEqual(summary["overall_status"], "pass")
        paths = _output_paths(summary)
        self.assertIn("product/PRD.md", paths)
        self.assertIn("product/roadmap.md", paths)


class CompoundProfileTest(ProfileTestBase):
    def test_compound_profile_pass(self) -> None:
        summary = self._run(
            brief={
                "name": "Test Compound",
                "target_job": "Bundle a skill and module together.",
                "target_profile": "compound",
                "compound_profiles": ["skill", "module"],
                "governor_ready": False,
            },
        )
        self.assertEqual(summary["target_profile"], "compound")
        self.assertEqual(summary["overall_status"], "pass")
        paths = _output_paths(summary)
        self.assertTrue(any("skill" in p for p in paths))
        self.assertTrue(any("module" in p for p in paths))


class ScoringOverridesTest(ProfileTestBase):
    def test_weight_override_applied(self) -> None:
        """Scoring overrides change the comparison weights."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RemixRuntime(output_root=tmpdir)
            summary = runtime.run(
                brief={
                    "name": "Override Test",
                    "target_job": "Test scoring overrides.",
                    "target_profile": "skill",
                    "governor_ready": False,
                    "scoring_overrides": {
                        "testability": {"weight": 5.0},
                        "structural_clarity": {"weight": 0.1},
                    },
                },
                sources=[
                    {"kind": "raw_text", "name": "src-a", "content": "# A\nDocs and guides."},
                    {"kind": "raw_text", "name": "src-b", "content": "# B\ndef test_x(): assert True"},
                ],
            )
            self.assertEqual(summary["overall_status"], "pass")
            scores_path = Path(summary["run_root"]) / "comparison_scores.json"
            comp = json.loads(scores_path.read_text())
            self.assertEqual(comp["weights"]["testability"], 5.0)
            self.assertEqual(comp["weights"]["structural_clarity"], 0.1)

    def test_fixed_score_injection(self) -> None:
        """Inject a fixed score for a custom dimension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RemixRuntime(output_root=tmpdir)
            summary = runtime.run(
                brief={
                    "name": "Custom Dim",
                    "target_job": "Test custom dimension injection.",
                    "target_profile": "module",
                    "governor_ready": False,
                    "scoring_overrides": {
                        "custom_quality": {"weight": 2.0, "score": 4.8},
                    },
                },
                sources=[
                    {"kind": "raw_text", "name": "src", "content": "# Module\n\nSimple module."},
                ],
            )
            self.assertEqual(summary["overall_status"], "pass")

            # Verify score was injected in analysis
            analysis_dir = Path(summary["run_root"]) / "analysis_reports"
            for f in analysis_dir.iterdir():
                report = json.loads(f.read_text())
                self.assertIn("custom_quality", report["scores"])
                self.assertAlmostEqual(report["scores"]["custom_quality"], 4.8, places=1)

            # Verify weight was applied in comparison
            scores_path = Path(summary["run_root"]) / "comparison_scores.json"
            comp = json.loads(scores_path.read_text())
            self.assertEqual(comp["weights"]["custom_quality"], 2.0)

    def test_scoring_overrides_empty_is_noop(self) -> None:
        """Empty scoring_overrides should not change behavior."""
        summary = self._run(
            brief={
                "name": "Noop Override",
                "target_job": "Test empty overrides.",
                "target_profile": "skill",
                "governor_ready": False,
                "scoring_overrides": {},
            },
        )
        self.assertEqual(summary["overall_status"], "pass")


class MultiSourceTest(ProfileTestBase):
    def test_three_sources_with_strategy_selection(self) -> None:
        sources = [
            {"kind": "raw_text", "name": "source-a", "content": "# A\n\nCore logic.\n\ndef main():\n    pass"},
            {"kind": "raw_text", "name": "source-b", "content": "# B\n\nTests.\n\ndef test_a():\n    assert True"},
            {"kind": "raw_text", "name": "source-c", "content": "# C\n\nDocs and guides.\n\n## Usage\nStep by step."},
        ]
        summary = self._run(
            brief={
                "name": "Multi Source",
                "target_job": "Combine three complementary sources.",
                "target_profile": "module",
                "governor_ready": False,
            },
            sources=sources,
        )
        self.assertEqual(summary["overall_status"], "pass")
        self.assertIsNotNone(summary["selected_strategy_id"])


class ConstraintGateTest(ProfileTestBase):
    def test_forbidden_license_gate(self) -> None:
        """Sources with forbidden licenses should be marked as failed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RemixRuntime(output_root=tmpdir)
            summary = runtime.run(
                brief={
                    "name": "Gate Test",
                    "target_job": "Test constraint gates.",
                    "target_profile": "skill",
                    "governor_ready": False,
                    "forbidden_licenses": ["GPL"],
                },
                sources=[
                    {
                        "kind": "raw_text",
                        "name": "gpl-source",
                        "content": "# GPL Licensed\n\nGNU General Public License v3.\n\ndef run(): pass",
                    },
                    {
                        "kind": "raw_text",
                        "name": "mit-source",
                        "content": "# MIT Licensed\n\nMIT License.\n\ndef run(): pass",
                    },
                ],
            )
            self.assertEqual(summary["overall_status"], "pass")

            gates_path = Path(summary["run_root"]) / "constraint_gates.json"
            gates = json.loads(gates_path.read_text())
            statuses = {g["source_id"]: g["passed"] for g in gates["gates"]}
            self.assertTrue(any(not passed for passed in statuses.values()))


if __name__ == "__main__":
    unittest.main()
