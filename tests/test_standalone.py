from __future__ import annotations

import tempfile
import unittest

from tests.test_support import SRC
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remix.runtime import RemixRuntime


class StandaloneRemixTests(unittest.TestCase):
    """Tests that run with zero external dependencies (no skill-se-kit)."""

    def test_runtime_creates_with_no_args(self) -> None:
        runtime = RemixRuntime()
        self.assertIsNotNone(runtime)

    def test_list_profiles(self) -> None:
        runtime = RemixRuntime()
        profiles = runtime.list_profiles()
        profile_ids = [p["profile_id"] for p in profiles]
        self.assertIn("skill", profile_ids)
        self.assertIn("module", profile_ids)
        self.assertIn("protocol", profile_ids)

    def test_detect_governor_returns_false_without_backend(self) -> None:
        runtime = RemixRuntime()
        self.assertFalse(runtime.detect_governor())

    def test_evolution_auto_detect_without_sekit(self) -> None:
        """Without skill-se-kit installed, auto-detect should disable evolution."""
        runtime = RemixRuntime()  # default: auto-detect
        status = runtime.evolution_status
        self.assertFalse(status["evolution_enabled"])
        self.assertEqual(status["backend"], "NullEvolutionBackend")

    def test_evolution_explicit_disable(self) -> None:
        """evolution=False should disable even if installed."""
        runtime = RemixRuntime(evolution=False)
        self.assertFalse(runtime.evolution_status["evolution_enabled"])

    def test_evolution_explicit_enable_raises_without_sekit(self) -> None:
        """evolution=True should raise if skill-se-kit not installed."""
        from remix.runtime import has_skill_se_kit
        if has_skill_se_kit():
            self.skipTest("skill-se-kit is installed")
        with self.assertRaises(ImportError):
            RemixRuntime(evolution=True)

    def test_full_run_with_raw_text_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RemixRuntime(output_root=tmpdir)
            summary = runtime.run(
                brief={
                    "name": "Test Module",
                    "target_job": "Produce a simple module from text sources.",
                    "target_profile": "module",
                    "packaging_profile": "python-package",
                    "transformation_mode": "harden",
                    "success_criteria": ["maintainability"],
                    "governor_ready": False,
                    "declared_interfaces": ["module.run"],
                },
                sources=[
                    {
                        "kind": "raw_text",
                        "name": "design-notes",
                        "content": "# Design\n\nA utility module for data transformation.\n\n## API\n\n- transform(data) -> result",
                    },
                    {
                        "kind": "raw_text",
                        "name": "requirements",
                        "content": "Must be pip-installable. Must have tests. Must include README.",
                    },
                ],
            )

            self.assertEqual(summary["overall_status"], "pass")
            self.assertEqual(summary["target_profile"], "module")
            self.assertIn("run_root", summary)
            self.assertTrue(len(summary["generated_outputs"]) > 0)

    def test_full_run_skill_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = RemixRuntime(output_root=tmpdir)
            summary = runtime.run(
                brief={
                    "name": "Review Skill",
                    "target_job": "Create a code review skill.",
                    "target_profile": "skill",
                    "transformation_mode": "consolidate",
                    "success_criteria": ["clear workflow"],
                    "governor_ready": False,
                    "declared_interfaces": ["review.execute"],
                },
                sources=[
                    {
                        "kind": "raw_text",
                        "name": "review-guide",
                        "content": "# Code Review Guide\n\n## Steps\n\n1. Read the diff\n2. Check for bugs\n3. Suggest improvements",
                    },
                ],
            )

            self.assertEqual(summary["overall_status"], "pass")
            self.assertEqual(summary["target_profile"], "skill")


if __name__ == "__main__":
    unittest.main()
