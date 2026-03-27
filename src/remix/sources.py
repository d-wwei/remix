from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from remix.utils import compact_excerpt, infer_license_name, limited, safe_read_text, slugify, top_words, utc_now_iso

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub repo URL detection
# ---------------------------------------------------------------------------
# Matches  https://github.com/{owner}/{repo}  (with optional trailing slash or .git)
# Does NOT match deeper paths like /blob/, /tree/, /issues, etc.
_GITHUB_REPO_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)

_DEFAULT_GITHUB_PATHS: List[str] = [
    "**/SKILL.md",
    "**/README.md",
    "**/manifest.json",
    "**/*.py",
]

# Maximum individual file fetches from a single repo (stay within rate limits).
_MAX_GITHUB_FILES = 40


def is_github_repo_url(url: str) -> bool:
    """Return True if *url* looks like a GitHub repository root URL."""
    return bool(_GITHUB_REPO_RE.match(url.strip()))


def parse_github_repo_url(url: str) -> Tuple[str, str] | None:
    """Extract (owner, repo) from a GitHub repo URL, or None."""
    m = _GITHUB_REPO_RE.match(url.strip())
    if m:
        return m.group("owner"), m.group("repo")
    return None


def _github_headers() -> Dict[str, str]:
    """Build HTTP headers for GitHub API calls.

    Respects the ``GITHUB_TOKEN`` environment variable for authenticated
    requests (5 000 req/hour instead of 60).
    """
    headers: Dict[str, str] = {
        "User-Agent": "remix/1.0",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_get(url: str, *, timeout: int = 15) -> bytes:
    """Perform a GET against the GitHub API / raw.githubusercontent.com.

    Raises ``RuntimeError`` with a human-friendly message on HTTP errors,
    including rate-limit (403/429) hints.
    """
    req = urllib.request.Request(url, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            remaining = exc.headers.get("X-RateLimit-Remaining", "?")
            reset = exc.headers.get("X-RateLimit-Reset", "?")
            raise RuntimeError(
                f"GitHub API rate limit hit ({exc.code}). "
                f"Remaining: {remaining}, resets at epoch {reset}. "
                "Set GITHUB_TOKEN env var for 5 000 req/hour."
            ) from exc
        raise RuntimeError(f"GitHub API error {exc.code} for {url}") from exc


def _match_paths(file_path: str, patterns: Sequence[str]) -> bool:
    """Return True if *file_path* matches any of the glob *patterns*.

    Each pattern is tested with ``fnmatch`` against both the full path and
    the basename, so ``**/*.py`` and ``*.py`` both match ``src/foo.py``.
    """
    basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    for pat in patterns:
        # Strip leading **/ for fnmatch compatibility (fnmatch does not
        # natively understand the recursive ** globstar).
        simple = pat.lstrip("*").lstrip("/")
        if fnmatch.fnmatch(file_path, pat):
            return True
        if fnmatch.fnmatch(basename, simple):
            return True
        if fnmatch.fnmatch(file_path, simple):
            return True
        # Also try the original pattern against just the basename.
        if fnmatch.fnmatch(basename, pat):
            return True
    return False


def expand_github_repo_source(source: Dict[str, Any] | str) -> Dict[str, Any]:
    """Normalise a source entry that may be a bare GitHub URL string.

    If *source* is a plain string matching a GitHub repo URL it is promoted
    to a ``{"kind": "github_repo", "url": ...}`` dict.  If *source* is
    already a dict whose ``url`` field is a GitHub repo URL and no ``kind``
    is set (or kind is ``"url"``), it is re-tagged as ``github_repo``.

    The function is idempotent: sources that are already ``github_repo``
    or that don't match are returned unchanged.
    """
    if isinstance(source, str):
        if is_github_repo_url(source):
            return {"kind": "github_repo", "url": source}
        # Not a GitHub repo URL -- return as-is (will be handled elsewhere).
        return {"kind": "raw_text", "content": source}

    url = source.get("url", "")
    if source.get("kind") in (None, "url") and is_github_repo_url(url):
        out = dict(source)
        out["kind"] = "github_repo"
        return out
    return source


TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".sh",
    ".sql",
    ".html",
    ".css",
}


class SourceAdapter:
    def normalize_sources(self, sources: Sequence[Dict[str, Any]], brief: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, source in enumerate(sources, start=1):
            # Auto-detect bare GitHub repo URL strings and untagged dicts.
            source = expand_github_repo_source(source)
            normalized.append(self._normalize_source(source, index=index, brief=brief))
        return normalized

    def _normalize_source(self, source: Dict[str, Any], *, index: int, brief: Dict[str, Any]) -> Dict[str, Any]:
        source_id = source.get("source_id") or f"source-{index:02d}-{slugify(source.get('name', source.get('kind', 'asset')))}"
        kind = source.get("kind", "raw_text")
        metadata = dict(source.get("metadata", {}))

        if kind in {"directory", "repository"}:
            payload = self._from_directory(source)
        elif kind == "github_repo":
            payload = self._from_github_repo(source)
        elif kind in {"file", "document"}:
            payload = self._from_file(source)
        elif kind in {"url", "github"}:
            payload = self._from_url(source)
        elif kind in {"raw_json", "json"}:
            payload = self._from_raw_json(source)
        else:
            payload = self._from_raw_text(source)

        artifact_types = source.get("artifact_types") or self._detect_artifact_types(payload["content"], payload["file_tree_summary"])
        license_name = metadata.get("license") or payload.get("license") or self._detect_license(payload)
        entrypoints = payload.get("entrypoints") or self._detect_entrypoints(payload["file_tree_summary"], payload["content"])
        docs_presence = payload.get("docs_presence", False)
        tests_presence = payload.get("tests_presence", False)
        manifest_presence = payload.get("manifest_presence", False)
        skill_md_presence = payload.get("skill_md_presence", False)
        metadata_quality = self._metadata_quality(metadata, license_name, payload)
        dependency_signals = self._dependency_signals(payload)
        maturity_signals = self._maturity_signals(payload)
        risk_signals = self._risk_signals(
            license_name=license_name,
            docs_presence=docs_presence,
            tests_presence=tests_presence,
            entrypoints=entrypoints,
            artifact_types=artifact_types,
        )
        target_lenses = self._target_lenses(payload, brief=brief, artifact_types=artifact_types)
        units = self._extract_units(payload["content"], payload["file_tree_summary"], source_id=source_id)

        return {
            "source_id": source_id,
            "source_kind": kind,
            "name": source.get("name", source_id),
            "location": payload.get("location"),
            "captured_at": utc_now_iso(),
            "version": source.get("version") or metadata.get("version") or payload.get("version", "unknown"),
            "artifact_types": artifact_types,
            "file_tree_summary": payload["file_tree_summary"],
            "manifest_presence": manifest_presence,
            "skill_md_presence": skill_md_presence,
            "docs_presence": docs_presence,
            "tests_presence": tests_presence,
            "entrypoints": entrypoints,
            "metadata_quality": metadata_quality,
            "license": license_name,
            "metadata": metadata,
            "maturity_signals": maturity_signals,
            "dependency_signals": dependency_signals,
            "operational_risk_signals": risk_signals,
            "content_summary": compact_excerpt(payload["content"], max_chars=500),
            "keywords": top_words(payload["content"]),
            "target_lenses": target_lenses,
            "units": units,
            "url_content_signals": payload.get("url_content_signals"),
        }

    def _from_directory(self, source: Dict[str, Any]) -> Dict[str, Any]:
        root = Path(source["path"]).expanduser().resolve()
        files = sorted(path for path in root.rglob("*") if path.is_file())
        file_tree = [str(path.relative_to(root)) for path in files[:80]]
        interesting_files = [path for path in files if path.suffix.lower() in TEXT_EXTENSIONS or path.name in {"SKILL.md", "LICENSE", "README"}]
        excerpts = []
        for path in interesting_files[:20]:
            rel = path.relative_to(root)
            excerpts.append(f"## {rel}\n{safe_read_text(path)[:3000]}")
        content = "\n\n".join(excerpts)
        return {
            "location": str(root),
            "content": content,
            "file_tree_summary": file_tree,
            "manifest_presence": any(path.name == "manifest.json" for path in files),
            "skill_md_presence": any(path.name == "SKILL.md" for path in files),
            "docs_presence": any("readme" in path.name.lower() or "docs" in path.parts for path in files),
            "tests_presence": any("test" in part.lower() for path in files for part in path.parts),
            "entrypoints": [item for item in file_tree if item.endswith(("main.py", "__init__.py", "package.json", "pyproject.toml", "manifest.json", "SKILL.md"))][:10],
            "license": self._read_license_from_directory(root),
        }

    def _from_github_repo(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch files from a GitHub repository and combine into a single source.

        The source dict must contain a ``url`` key pointing to a GitHub repo.
        An optional ``paths`` key provides glob patterns to filter the tree;
        when omitted the default skill-oriented patterns are used.
        """
        url = source["url"]
        parsed = parse_github_repo_url(url)
        if parsed is None:
            raise ValueError(f"Not a valid GitHub repo URL: {url}")
        owner, repo = parsed
        path_patterns: List[str] = source.get("paths") or list(_DEFAULT_GITHUB_PATHS)
        branch = source.get("branch", "HEAD")

        # 1. Fetch the recursive file tree via the Git Trees API.
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        try:
            tree_data = json.loads(_github_get(tree_url))
        except RuntimeError as exc:
            logger.warning("GitHub tree fetch failed for %s/%s: %s", owner, repo, exc)
            return {
                "location": url,
                "content": f"[error fetching repo tree: {exc}]",
                "file_tree_summary": [],
                "docs_presence": False,
                "tests_presence": False,
            }

        if "tree" not in tree_data:
            logger.warning("Unexpected GitHub API response for %s/%s (no tree key)", owner, repo)
            return {
                "location": url,
                "content": "[GitHub API returned no tree data]",
                "file_tree_summary": [],
                "docs_presence": False,
                "tests_presence": False,
            }

        # All blob entries (files) from the tree.
        all_files: List[str] = [
            entry["path"]
            for entry in tree_data["tree"]
            if entry.get("type") == "blob"
        ]

        # 2. Filter files by the requested glob patterns.
        matched_files = [f for f in all_files if _match_paths(f, path_patterns)]

        # Also always include LICENSE if present (for license detection).
        license_files = [
            f for f in all_files
            if f.upper().startswith("LICENSE") or f.upper() == "COPYING"
        ]
        for lf in license_files:
            if lf not in matched_files:
                matched_files.append(lf)

        # Cap the number of files to fetch.
        matched_files = matched_files[:_MAX_GITHUB_FILES]

        # Build a complete file tree summary from the repo (capped).
        file_tree_summary = all_files[:80]

        # 3. Fetch each matched file's content via raw.githubusercontent.
        # Resolve the default branch name from the tree URL response.
        default_branch = tree_data.get("url", "").rsplit("/", 1)[-1] if branch == "HEAD" else branch
        if not default_branch or default_branch == "HEAD":
            try:
                repo_info = json.loads(
                    _github_get(f"https://api.github.com/repos/{owner}/{repo}")
                )
                default_branch = repo_info.get("default_branch", "main")
            except RuntimeError:
                default_branch = "main"

        excerpts: List[str] = []
        fetched_count = 0
        failed_count = 0
        for file_path in matched_files:
            raw_url = (
                f"https://raw.githubusercontent.com/{owner}/{repo}"
                f"/{default_branch}/{file_path}"
            )
            try:
                raw_bytes = _github_get(raw_url, timeout=10)
                text = raw_bytes.decode("utf-8", errors="replace")
                excerpts.append(f"## {file_path}\n{text[:3000]}")
                fetched_count += 1
            except RuntimeError as exc:
                logger.debug("Failed to fetch %s: %s", raw_url, exc)
                failed_count += 1

        content = "\n\n".join(excerpts)

        # 4. Derive metadata signals.
        return {
            "location": url,
            "content": content,
            "file_tree_summary": file_tree_summary,
            "manifest_presence": any(f.endswith("manifest.json") for f in all_files),
            "skill_md_presence": any(f.endswith("SKILL.md") for f in all_files),
            "docs_presence": any(
                "readme" in f.lower() or "docs" in f.lower().split("/")
                for f in all_files
            ),
            "tests_presence": any(
                "test" in part.lower() for f in all_files for part in f.split("/")
            ),
            "entrypoints": [
                f for f in all_files
                if f.endswith((
                    "main.py", "__init__.py", "package.json",
                    "pyproject.toml", "manifest.json", "SKILL.md",
                ))
            ][:10],
            "license": self._detect_license_from_content(excerpts),
            "version": tree_data.get("sha", "unknown")[:12],
            "github_repo_meta": {
                "owner": owner,
                "repo": repo,
                "branch": default_branch,
                "total_files": len(all_files),
                "matched_files": len(matched_files),
                "fetched_files": fetched_count,
                "failed_files": failed_count,
                "path_patterns": path_patterns,
            },
        }

    def _detect_license_from_content(self, excerpts: List[str]) -> str | None:
        """Try to detect a license from fetched file excerpts."""
        for excerpt in excerpts:
            if excerpt.startswith("## LICENSE") or excerpt.startswith("## COPYING"):
                license_text = excerpt.split("\n", 1)[-1] if "\n" in excerpt else excerpt
                return infer_license_name(license_text)
        return None

    def _from_file(self, source: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(source["path"]).expanduser().resolve()
        content = safe_read_text(path)
        return {
            "location": str(path),
            "content": content,
            "file_tree_summary": [path.name],
            "manifest_presence": path.name == "manifest.json",
            "skill_md_presence": path.name == "SKILL.md",
            "docs_presence": path.suffix.lower() == ".md",
            "tests_presence": "test" in path.name.lower(),
        }

    def _from_url(self, source: Dict[str, Any]) -> Dict[str, Any]:
        url = source["url"]
        request = urllib.request.Request(url, headers={"User-Agent": "remix/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
        content = raw.decode("utf-8", errors="replace")
        signals = _analyze_url_content(content)
        return {
            "location": url,
            "content": content,
            "file_tree_summary": [url],
            "docs_presence": True,
            "tests_presence": False,
            "url_content_signals": signals,
        }

    def _from_raw_text(self, source: Dict[str, Any]) -> Dict[str, Any]:
        content = source.get("content", "")
        return {
            "location": source.get("location", "inline"),
            "content": content,
            "file_tree_summary": [source.get("name", "inline.txt")],
            "docs_presence": True,
            "tests_presence": False,
        }

    def _from_raw_json(self, source: Dict[str, Any]) -> Dict[str, Any]:
        payload = source.get("content")
        if isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(payload, indent=2, sort_keys=False)
        return {
            "location": source.get("location", "inline.json"),
            "content": content,
            "file_tree_summary": [source.get("name", "inline.json")],
            "manifest_presence": '"schema_name": "SkillManifest"' in content,
            "docs_presence": False,
            "tests_presence": False,
        }

    def _read_license_from_directory(self, root: Path) -> str | None:
        for name in ("LICENSE", "LICENSE.txt", "COPYING"):
            candidate = root / name
            if candidate.exists():
                return infer_license_name(safe_read_text(candidate))
        return None

    def _detect_artifact_types(self, content: str, file_tree: Sequence[str]) -> List[str]:
        lowered = content.lower()
        paths = " ".join(file_tree).lower()
        detected: List[str] = []
        if "skill.md" in paths or '"schema_name": "skillmanifest"' in lowered or "skill_id" in lowered:
            detected.append("skill")
        if "schema" in paths or '"$schema"' in lowered or "protocol" in lowered:
            detected.append("protocol")
        if any(token in paths for token in ("pyproject.toml", "package.json", "src/", "__init__.py", "setup.py")):
            detected.append("module")
        if any(token in lowered for token in ("rollout", "feature flag", "acceptance criteria", "instrumentation")):
            detected.append("feature")
        if any(token in lowered for token in ("prd", "roadmap", "journey", "user story", "capability map")):
            detected.append("product")
        return detected or ["generic"]

    def _detect_entrypoints(self, file_tree: Sequence[str], content: str) -> List[str]:
        entrypoints = [
            path
            for path in file_tree
            if path.endswith(("SKILL.md", "manifest.json", "main.py", "__init__.py", "package.json", "pyproject.toml"))
        ]
        if not entrypoints and "def main(" in content:
            entrypoints.append("def main()")
        return limited(entrypoints, limit=10)

    def _detect_license(self, payload: Dict[str, Any]) -> str:
        if payload.get("license"):
            return payload["license"]
        return infer_license_name(payload["content"])

    def _metadata_quality(self, metadata: Dict[str, Any], license_name: str, payload: Dict[str, Any]) -> str:
        score = 0
        score += 1 if metadata else 0
        score += 1 if license_name != "unknown" else 0
        score += 1 if payload.get("manifest_presence") else 0
        score += 1 if payload.get("docs_presence") else 0
        if score >= 3:
            return "high"
        if score == 2:
            return "medium"
        return "low"

    def _dependency_signals(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload["content"].lower()
        dependencies = 0
        dependencies += text.count("dependencies")
        dependencies += text.count("requires")
        dependencies += text.count("import ")
        return {
            "dependency_mentions": dependencies,
            "package_manifest_present": any(item.endswith(("pyproject.toml", "package.json", "setup.py")) for item in payload["file_tree_summary"]),
        }

    def _maturity_signals(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tree = payload["file_tree_summary"]
        return {
            "file_count": len(tree),
            "docs_present": payload.get("docs_presence", False),
            "tests_present": payload.get("tests_presence", False),
            "examples_present": any("example" in path.lower() for path in tree),
            "manifest_present": payload.get("manifest_presence", False),
        }

    def _risk_signals(
        self,
        *,
        license_name: str,
        docs_presence: bool,
        tests_presence: bool,
        entrypoints: Sequence[str],
        artifact_types: Sequence[str],
    ) -> List[str]:
        risks: List[str] = []
        if license_name == "unknown":
            risks.append("license is unknown")
        if not docs_presence:
            risks.append("documentation is thin")
        if not tests_presence:
            risks.append("tests are missing or not discoverable")
        if not entrypoints:
            risks.append("entrypoints are unclear")
        if artifact_types == ["generic"]:
            risks.append("artifact type is weakly specified")
        return risks

    def _target_lenses(self, payload: Dict[str, Any], *, brief: Dict[str, Any], artifact_types: Sequence[str]) -> Dict[str, Any]:
        target_profile = brief.get("target_profile") or brief.get("target_artifact_type") or "skill"
        return {
            "target_profile": target_profile,
            "native_match": target_profile in artifact_types,
            "contains_tests": payload.get("tests_presence", False),
            "contains_docs": payload.get("docs_presence", False),
        }

    def _extract_units(self, content: str, file_tree: Sequence[str], *, source_id: str) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        units.extend(self._markdown_units(content, source_id=source_id))
        units.extend(self._json_units(content, source_id=source_id))
        units.extend(self._code_units(content, source_id=source_id))
        if not units:
            paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", content) if chunk.strip()]
            for index, paragraph in enumerate(paragraphs[:8], start=1):
                units.append(
                    {
                        "unit_id": f"{source_id}:paragraph:{index}",
                        "kind": "paragraph",
                        "name": f"Paragraph {index}",
                        "summary": compact_excerpt(paragraph, max_chars=180),
                    }
                )
        if file_tree:
            for path in limited(list(file_tree), limit=6):
                units.append(
                    {
                        "unit_id": f"{source_id}:file:{path}",
                        "kind": "file",
                        "name": path,
                        "summary": f"File contribution from {path}",
                    }
                )
        return limited(units, limit=20)

    def _markdown_units(self, content: str, *, source_id: str) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        sections = re.split(r"(?m)^#{1,6}\s+", content)
        headings = re.findall(r"(?m)^#{1,6}\s+(.+)$", content)
        for index, heading in enumerate(headings[:8], start=1):
            section_text = sections[index] if index < len(sections) else ""
            units.append(
                {
                    "unit_id": f"{source_id}:heading:{index}",
                    "kind": "heading",
                    "name": heading.strip(),
                    "summary": compact_excerpt(section_text, max_chars=180),
                }
            )
        return units

    def _json_units(self, content: str, *, source_id: str) -> List[Dict[str, Any]]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        units: List[Dict[str, Any]] = []
        for key, value in list(payload.items())[:10]:
            units.append(
                {
                    "unit_id": f"{source_id}:json:{key}",
                    "kind": "json-key",
                    "name": key,
                    "summary": compact_excerpt(json.dumps(value, ensure_ascii=True), max_chars=160),
                }
            )
        return units

    def _code_units(self, content: str, *, source_id: str) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        patterns: Iterable[Tuple[str, str]] = [
            ("class", r"(?m)^class\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("function", r"(?m)^(?:def|function)\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("export", r"(?m)^export\s+(?:const|function|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ]
        for kind, pattern in patterns:
            for name in re.findall(pattern, content)[:6]:
                units.append(
                    {
                        "unit_id": f"{source_id}:{kind}:{name}",
                        "kind": kind,
                        "name": name,
                        "summary": f"{kind} unit {name}",
                    }
                )
        return units


def _analyze_url_content(content: str) -> Dict[str, Any]:
    """Extract differentiating structural signals from URL content.

    Returns a dict of numeric signals that downstream scoring can use
    to distinguish URL sources from each other.
    """
    lines = content.split("\n")
    total_lines = len(lines)
    words = content.split()
    word_count = len(words)

    # --- Heading analysis (depth and count) ---
    heading_counts: Dict[int, int] = {}
    for line in lines:
        match = re.match(r"^(#{1,6})\s+", line)
        if match:
            level = len(match.group(1))
            heading_counts[level] = heading_counts.get(level, 0) + 1
    total_headings = sum(heading_counts.values())
    max_heading_depth = max(heading_counts.keys()) if heading_counts else 0

    # --- Rule/instruction density ---
    # Lines starting with -, *, numbered items (1. 2. etc.), or imperative verbs
    list_item_pattern = re.compile(r"^\s*[-*]\s+\S|^\s*\d+[.)]\s+\S")
    imperative_pattern = re.compile(
        r"^\s*(?:must|should|shall|ensure|verify|check|use|do|don\'t|never|always|avoid|prefer|consider|create|add|remove|set|run|define|implement|include|provide|make|keep|return|call|pass|validate|handle|configure|specify)\b",
        re.IGNORECASE,
    )
    list_items = 0
    imperative_lines = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if list_item_pattern.match(line):
            list_items += 1
        if imperative_pattern.match(stripped):
            imperative_lines += 1
    rule_density = list_items + imperative_lines

    # --- Code block count ---
    code_blocks = len(re.findall(r"(?m)^```", content))
    # Fenced blocks have open+close, so divide by 2 for paired blocks
    code_block_pairs = code_blocks // 2

    # Also count indented code blocks (4+ spaces after a blank line)
    indented_code_sections = 0
    prev_blank = True
    for line in lines:
        if not line.strip():
            prev_blank = True
            continue
        if prev_blank and line.startswith("    ") and not line.strip().startswith(("-", "*", "#")):
            indented_code_sections += 1
            prev_blank = False
        else:
            prev_blank = False
    total_code_blocks = code_block_pairs + indented_code_sections

    # --- Unique vocabulary richness ---
    # Count distinct meaningful words (3+ chars, not purely numeric)
    word_re = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
    unique_words = set(word_re.findall(content.lower()))
    vocabulary_size = len(unique_words)
    # Richness: unique words / total words (higher = more diverse vocabulary)
    vocabulary_richness = vocabulary_size / max(word_count, 1)

    # --- Link density (external references) ---
    link_count = len(re.findall(r"\[.*?\]\(.*?\)|https?://\S+", content))

    # --- Table presence ---
    table_rows = len(re.findall(r"(?m)^\|.*\|$", content))

    return {
        "word_count": word_count,
        "line_count": total_lines,
        "heading_count": total_headings,
        "max_heading_depth": max_heading_depth,
        "heading_counts_by_level": heading_counts,
        "list_item_count": list_items,
        "imperative_line_count": imperative_lines,
        "rule_density": rule_density,
        "code_block_count": total_code_blocks,
        "vocabulary_size": vocabulary_size,
        "vocabulary_richness": round(vocabulary_richness, 4),
        "link_count": link_count,
        "table_row_count": table_rows,
    }
