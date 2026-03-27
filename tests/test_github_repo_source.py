"""Tests for the github_repo source kind in remix.sources."""
from __future__ import annotations

import json
import sys
import unittest
from unittest.mock import patch

from tests.test_support import SRC

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remix.sources import (
    SourceAdapter,
    _DEFAULT_GITHUB_PATHS,
    _match_paths,
    expand_github_repo_source,
    is_github_repo_url,
    parse_github_repo_url,
)


# ---------------------------------------------------------------------------
# URL detection
# ---------------------------------------------------------------------------
class TestIsGithubRepoUrl(unittest.TestCase):
    def test_standard_url(self) -> None:
        self.assertTrue(is_github_repo_url("https://github.com/org/repo"))

    def test_trailing_slash(self) -> None:
        self.assertTrue(is_github_repo_url("https://github.com/org/repo/"))

    def test_dot_git_suffix(self) -> None:
        self.assertTrue(is_github_repo_url("https://github.com/org/repo.git"))

    def test_http(self) -> None:
        self.assertTrue(is_github_repo_url("http://github.com/org/repo"))

    def test_with_hyphens_and_dots(self) -> None:
        self.assertTrue(is_github_repo_url("https://github.com/my-org/my.repo"))

    def test_deeper_path_rejected(self) -> None:
        self.assertFalse(is_github_repo_url("https://github.com/org/repo/blob/main/README.md"))
        self.assertFalse(is_github_repo_url("https://github.com/org/repo/tree/main"))
        self.assertFalse(is_github_repo_url("https://github.com/org/repo/issues"))

    def test_not_github(self) -> None:
        self.assertFalse(is_github_repo_url("https://gitlab.com/org/repo"))

    def test_raw_githubusercontent(self) -> None:
        self.assertFalse(is_github_repo_url("https://raw.githubusercontent.com/org/repo/main/f.md"))

    def test_empty_and_garbage(self) -> None:
        self.assertFalse(is_github_repo_url(""))
        self.assertFalse(is_github_repo_url("not a url"))


class TestParseGithubRepoUrl(unittest.TestCase):
    def test_parse_standard(self) -> None:
        result = parse_github_repo_url("https://github.com/acme/widgets")
        self.assertEqual(result, ("acme", "widgets"))

    def test_parse_with_git_suffix(self) -> None:
        result = parse_github_repo_url("https://github.com/acme/widgets.git")
        self.assertEqual(result, ("acme", "widgets"))

    def test_parse_non_github_returns_none(self) -> None:
        self.assertIsNone(parse_github_repo_url("https://example.com/foo/bar"))


# ---------------------------------------------------------------------------
# Path matching
# ---------------------------------------------------------------------------
class TestMatchPaths(unittest.TestCase):
    def test_star_star_star_py(self) -> None:
        self.assertTrue(_match_paths("src/foo.py", ["**/*.py"]))

    def test_star_md(self) -> None:
        self.assertTrue(_match_paths("README.md", ["**/*.md"]))

    def test_exact_name(self) -> None:
        self.assertTrue(_match_paths("docs/SKILL.md", ["**/SKILL.md"]))

    def test_no_match(self) -> None:
        self.assertFalse(_match_paths("image.png", ["**/*.py", "**/*.md"]))

    def test_root_level_file(self) -> None:
        self.assertTrue(_match_paths("setup.py", ["**/*.py"]))

    def test_manifest_json(self) -> None:
        self.assertTrue(_match_paths("manifest.json", ["**/manifest.json"]))
        self.assertTrue(_match_paths("sub/dir/manifest.json", ["**/manifest.json"]))


# ---------------------------------------------------------------------------
# expand_github_repo_source
# ---------------------------------------------------------------------------
class TestExpandGithubRepoSource(unittest.TestCase):
    def test_bare_string_url(self) -> None:
        result = expand_github_repo_source("https://github.com/org/repo")
        self.assertEqual(result["kind"], "github_repo")
        self.assertEqual(result["url"], "https://github.com/org/repo")

    def test_bare_string_non_github(self) -> None:
        result = expand_github_repo_source("just some text")
        self.assertEqual(result["kind"], "raw_text")

    def test_dict_with_url_no_kind(self) -> None:
        result = expand_github_repo_source({"url": "https://github.com/org/repo"})
        self.assertEqual(result["kind"], "github_repo")

    def test_dict_with_url_kind_url(self) -> None:
        result = expand_github_repo_source({"kind": "url", "url": "https://github.com/org/repo"})
        self.assertEqual(result["kind"], "github_repo")

    def test_already_github_repo_unchanged(self) -> None:
        src = {"kind": "github_repo", "url": "https://github.com/org/repo"}
        result = expand_github_repo_source(src)
        self.assertEqual(result["kind"], "github_repo")

    def test_non_github_dict_unchanged(self) -> None:
        src = {"kind": "file", "path": "/tmp/foo.md"}
        result = expand_github_repo_source(src)
        self.assertEqual(result["kind"], "file")


# ---------------------------------------------------------------------------
# _from_github_repo (with mocked network calls)
# ---------------------------------------------------------------------------
# Fake tree response from the GitHub API
_FAKE_TREE = {
    "sha": "abc123def456",
    "url": "https://api.github.com/repos/acme/widgets/git/trees/main",
    "tree": [
        {"path": "README.md", "type": "blob", "size": 100},
        {"path": "SKILL.md", "type": "blob", "size": 200},
        {"path": "src/__init__.py", "type": "blob", "size": 50},
        {"path": "src/core.py", "type": "blob", "size": 1000},
        {"path": "tests/test_core.py", "type": "blob", "size": 800},
        {"path": "manifest.json", "type": "blob", "size": 300},
        {"path": "LICENSE", "type": "blob", "size": 1100},
        {"path": "docs/guide.md", "type": "blob", "size": 500},
        {"path": "assets/logo.png", "type": "blob", "size": 50000},
        {"path": "src", "type": "tree"},  # directory entry, should be skipped
    ],
}


def _fake_github_get(url: str, *, timeout: int = 15) -> bytes:
    """Mock _github_get that returns canned responses."""
    if "git/trees" in url:
        return json.dumps(_FAKE_TREE).encode()
    # raw file content requests
    if "raw.githubusercontent.com" in url:
        filename = url.rsplit("/", 1)[-1]
        return f"# Content of {filename}\nSome text here.\n".encode()
    return b"{}"


class TestFromGithubRepo(unittest.TestCase):
    @patch("remix.sources._github_get", side_effect=_fake_github_get)
    def test_basic_fetch(self, mock_get) -> None:
        adapter = SourceAdapter()
        source = {"kind": "github_repo", "url": "https://github.com/acme/widgets"}
        payload = adapter._from_github_repo(source)

        self.assertEqual(payload["location"], "https://github.com/acme/widgets")
        # Should have fetched files matching default patterns
        self.assertIn("content", payload)
        self.assertTrue(len(payload["content"]) > 0)
        # file_tree_summary should list repo files
        self.assertIn("README.md", payload["file_tree_summary"])
        self.assertIn("src/core.py", payload["file_tree_summary"])
        # Metadata signals
        self.assertTrue(payload["manifest_presence"])
        self.assertTrue(payload["skill_md_presence"])
        self.assertTrue(payload["docs_presence"])
        self.assertTrue(payload["tests_presence"])
        # github_repo_meta
        meta = payload["github_repo_meta"]
        self.assertEqual(meta["owner"], "acme")
        self.assertEqual(meta["repo"], "widgets")
        self.assertGreater(meta["fetched_files"], 0)

    @patch("remix.sources._github_get", side_effect=_fake_github_get)
    def test_custom_paths_filter(self, mock_get) -> None:
        adapter = SourceAdapter()
        source = {
            "kind": "github_repo",
            "url": "https://github.com/acme/widgets",
            "paths": ["**/*.md"],
        }
        payload = adapter._from_github_repo(source)
        meta = payload["github_repo_meta"]
        self.assertEqual(meta["path_patterns"], ["**/*.md"])
        # Should match README.md, SKILL.md, docs/guide.md + LICENSE (always included)
        self.assertGreaterEqual(meta["matched_files"], 3)

    @patch("remix.sources._github_get", side_effect=RuntimeError("rate limit"))
    def test_tree_fetch_failure_graceful(self, mock_get) -> None:
        adapter = SourceAdapter()
        source = {"kind": "github_repo", "url": "https://github.com/acme/widgets"}
        payload = adapter._from_github_repo(source)
        # Should not raise -- returns a degraded payload
        self.assertIn("error", payload["content"])
        self.assertEqual(payload["file_tree_summary"], [])


# ---------------------------------------------------------------------------
# Full normalize_sources integration (with mocked network)
# ---------------------------------------------------------------------------
class TestNormalizeSourcesGithubRepo(unittest.TestCase):
    @patch("remix.sources._github_get", side_effect=_fake_github_get)
    def test_normalize_bare_github_url(self, mock_get) -> None:
        adapter = SourceAdapter()
        brief = {"target_profile": "skill"}
        # Pass a bare URL string as a source entry
        sources = ["https://github.com/acme/widgets"]
        result = adapter.normalize_sources(sources, brief)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_kind"], "github_repo")
        self.assertEqual(result[0]["location"], "https://github.com/acme/widgets")

    @patch("remix.sources._github_get", side_effect=_fake_github_get)
    def test_normalize_dict_source(self, mock_get) -> None:
        adapter = SourceAdapter()
        brief = {"target_profile": "skill"}
        sources = [{"kind": "github_repo", "url": "https://github.com/acme/widgets", "paths": ["**/*.py"]}]
        result = adapter.normalize_sources(sources, brief)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_kind"], "github_repo")


# ---------------------------------------------------------------------------
# CLI _load_sources_arg
# ---------------------------------------------------------------------------
class TestLoadSourcesArg(unittest.TestCase):
    def test_bare_github_url(self) -> None:
        from remix.cli import _load_sources_arg  # noqa: WPS433
        result = _load_sources_arg("https://github.com/acme/widgets")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "github_repo")
        self.assertEqual(result[0]["url"], "https://github.com/acme/widgets")

    def test_json_array_passthrough(self) -> None:
        from remix.cli import _load_sources_arg
        result = _load_sources_arg('[{"kind": "raw_text", "content": "hello"}]')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "raw_text")

    def test_json_object_wrapped_in_list(self) -> None:
        from remix.cli import _load_sources_arg
        result = _load_sources_arg('{"kind": "raw_text", "content": "hello"}')
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
