from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_support import PROTOCOL_ROOT, has_skill_se_kit, load_example_manifest


@unittest.skipUnless(has_skill_se_kit(), "skill-se-kit not installed")
class RemixRuntimeTests(unittest.TestCase):
    def _runtime(self, root: str):
        from remix.runtime import from_skill_runtime

        runtime = from_skill_runtime(skill_root=root, protocol_root=PROTOCOL_ROOT)
        manifest = load_example_manifest("standalone.manifest.json")
        manifest["skill_id"] = "remix.core"
        manifest["name"] = "Remix"
        manifest["description"] = "Native Remix runtime."
        runtime.bootstrap(manifest)
        return runtime

    def _write_skill_source(self, root: Path, *, name: str, skill_id: str) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(
            "\n".join(
                [
                    f"# {name}",
                    "",
                    "## Purpose",
                    "Handle synthesis and review workflows.",
                    "",
                    "## Workflow",
                    "- intake",
                    "- compare",
                    "- review",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            """
{
  "schema_name": "SkillManifest",
  "schema_version": "1.0.0",
  "protocol_version": "1.0.0",
  "skill_id": "%s",
  "name": "%s",
  "version": "0.1.0",
  "description": "Source skill",
  "governance": {"mode": "standalone", "official_status": "local"},
  "capability": {"level": "native", "summary": "source skill"},
  "compatibility": {"min_protocol_version": "1.0.0", "max_protocol_version": "1.0.0"},
  "metadata": {"owner": "tests"}
}
"""
            % (skill_id, name),
            encoding="utf-8",
        )
        (root / "README.md").write_text("# README\n\nIncludes docs.\n", encoding="utf-8")
        tests_dir = root / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_smoke.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    def test_skill_profile_run_generates_governor_ready_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._runtime(tmpdir)
            source_a = Path(tmpdir) / "sources" / "skill_a"
            source_b = Path(tmpdir) / "sources" / "skill_b"
            self._write_skill_source(source_a, name="Source A", skill_id="source.a")
            self._write_skill_source(source_b, name="Source B", skill_id="source.b")

            summary = runtime.run(
                brief={
                    "name": "Remixed Review Skill",
                    "target_job": "Combine the strongest review and synthesis patterns into a governed-ready skill.",
                    "target_profile": "skill",
                    "transformation_mode": "consolidate",
                    "success_criteria": ["protocol compatibility", "clear workflow", "tests"],
                    "governor_ready": True,
                    "declared_interfaces": ["review.execute", "review.compare"],
                },
                sources=[
                    {"kind": "directory", "path": str(source_a), "name": "source-a"},
                    {"kind": "directory", "path": str(source_b), "name": "source-b"},
                ],
            )

            self.assertEqual(summary["overall_status"], "pass")
            run_root = Path(summary["run_root"])
            import json
            generated_manifest = json.loads((run_root / "remixed_output" / "skill" / "manifest.json").read_text(encoding="utf-8"))
            runtime.validator.validate_manifest(generated_manifest)
            proposal = json.loads((run_root / "release_bundle" / "governor_candidate" / "skill_proposal.json").read_text(encoding="utf-8"))
            runtime.validator.validate_proposal(proposal)
            self.assertTrue((run_root / "audit" / "audit_summary.md").exists())
            self.assertTrue((run_root / "verification_report.md").exists())

    def test_module_profile_run_generates_wrapper_and_python_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._runtime(tmpdir)
            module_root = Path(tmpdir) / "sources" / "module_source"
            module_root.mkdir(parents=True, exist_ok=True)
            (module_root / "pyproject.toml").write_text(
                """
[project]
name = "source-module"
version = "0.1.0"
description = "Module source"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            package_dir = module_root / "src" / "source_module"
            package_dir.mkdir(parents=True, exist_ok=True)
            (package_dir / "__init__.py").write_text(
                "def calculate():\n    return {'status': 'ok'}\n",
                encoding="utf-8",
            )
            (module_root / "README.md").write_text(
                "# PRD\n\nFeature rollout and module packaging guidance.\n",
                encoding="utf-8",
            )

            summary = runtime.run(
                brief={
                    "name": "Remixed Module",
                    "target_job": "Produce a reusable implementation module with strong handoff metadata.",
                    "target_profile": "module",
                    "packaging_profile": "python-package",
                    "transformation_mode": "harden",
                    "success_criteria": ["maintainability", "tests"],
                    "governor_ready": True,
                    "declared_interfaces": ["module.get_blueprint"],
                },
                sources=[
                    {"kind": "directory", "path": str(module_root), "name": "module-source"},
                    {"kind": "raw_text", "name": "product-note", "content": "# Roadmap\n\nNeed better packaging and provenance."},
                ],
            )

            self.assertEqual(summary["overall_status"], "pass")
            run_root = Path(summary["run_root"])
            self.assertTrue((run_root / "remixed_output" / "module" / "pyproject.toml").exists())
            self.assertTrue((run_root / "release_bundle" / "companion_skill_wrapper.json").exists())
            self.assertTrue((run_root / "handoff_report.md").exists())


if __name__ == "__main__":
    unittest.main()
