# Remix

## Identity

- **name**: Remix
- **version**: 0.2.0
- **type**: artifact-reconstruction-tool
- **language**: Python (CLI interface available for any agent)

## What It Does

Remix analyzes, compares, and reconstructs artifacts. Given a brief (what you want) and sources (what you have), it:

1. Normalizes and scores each source across configurable dimensions
2. Ranks sources, applies hard gates, identifies complementary pairs
3. Synthesizes 2–3 strategy options (conservative, balanced, forward-port)
4. Builds the selected output artifact with full provenance and audit trail
5. Verifies the result against profile-specific checks

## Supported Target Profiles

| Profile | Output | Use Case |
|---------|--------|----------|
| `skill` | manifest.json + SKILL.md + tests.md | Agent skills |
| `protocol` | schema.json + examples + compatibility matrix | Interop contracts |
| `module` | package layout + source + tests | Reusable code packages |
| `feature` | spec + rollout plan + acceptance criteria | Product features |
| `product` | PRD + roadmap + capability map | Product definitions |
| `compound` | Recursive bundle of above profiles | Multi-artifact systems |

## How to Invoke

### CLI (any agent that can run shell commands)

```bash
# List available profiles
remix profiles

# Analyze sources (scores only, no build)
remix analyze \
  --brief '{"target_profile":"skill","target_job":"evaluate sources"}' \
  --sources '[{"kind":"file","path":"./source.md"}]'

# Compare sources (rankings + strategy options, no build)
remix compare \
  --brief '{"target_profile":"skill","target_job":"pick the best source"}' \
  --sources '[{"kind":"file","path":"./a.md"},{"kind":"file","path":"./b.md"}]'

# Run the full pipeline (analyze + compare + build + verify)
remix run \
  --brief '{"target_profile":"skill","target_job":"build a code review skill"}' \
  --sources '[{"kind":"file","path":"./existing-skill.md"}]' \
  --output ./output

# Brief and sources can also be JSON file paths
remix run --brief brief.json --sources sources.json
```

### Python API (for Python-based agents)

```python
from remix import RemixRuntime

runtime = RemixRuntime(output_root="./output")
summary = runtime.run(
    brief={"target_profile": "skill", "target_job": "..."},
    sources=[{"kind": "file", "path": "./source.md"}],
)
```

## Input Format

### Brief

```json
{
  "target_profile": "skill|protocol|module|feature|product|compound",
  "target_job": "what the output should accomplish",
  "name": "artifact name",
  "version": "0.1.0",
  "success_criteria": ["criterion1", "criterion2"],
  "constraints": ["constraint1"],
  "scoring_overrides": {
    "task_fit": {"weight": 1.5},
    "testability": {"weight": 0.5}
  }
}
```

### Sources

```json
[
  {"kind": "file", "path": "/path/to/artifact.md"},
  {"kind": "directory", "path": "/path/to/project/"},
  {"kind": "url", "url": "https://example.com/spec.json"},
  {"kind": "raw_text", "content": "inline content here"}
]
```

## Output

A structured workspace under `{output}/runs/{run_id}/` containing:

- `remixed_output/` — the rebuilt artifact (profile-specific files)
- `audit/` — provenance, risk register, decision log
- `verification_report.md` — pass/warn/fail checks
- `release_bundle/run_summary.json` — machine-readable summary

The CLI prints a JSON summary to stdout.

## Extension Points

- **Custom scoring weights**: Override per-dimension weights via `scoring_overrides` in the brief
- **Analyzer plugin**: Implement the `Analyzer` protocol to replace heuristic scoring with LLM-backed or custom analysis
- **Validator plugin**: Implement the `Validator` protocol to add custom manifest/proposal validation
- **EvolutionBackend plugin**: Implement the `EvolutionBackend` protocol to record experience for self-improvement (e.g., via Skill-SE-Kit)

## Self-Evolution (skill-se-kit)

Remix integrates with `skill-se-kit` for experience recording and self-improvement.

**Default behavior: auto-detect and enable.**

- If `skill-se-kit` is installed → evolution is **enabled** automatically
- If `skill-se-kit` is not installed → Remix works fully without it, no error
- User says "don't use evolution" → pass `--no-evolution` (CLI) or `evolution=False` (Python)

When using Remix as an agent tool:
1. Check the `evolution` field in the output JSON to see current status
2. If `skill_se_kit_installed: false`, optionally ask the user: "skill-se-kit is not installed. Want to enable self-evolution? (`pip install remix[evolution]`)"
3. If the user explicitly declines, pass `--no-evolution`
4. Never require the user to install it — Remix works fully without it

### CLI

```bash
# Default: auto-detect (enabled if installed)
remix run --brief '...' --sources '...'

# Explicit disable
remix run --no-evolution --brief '...' --sources '...'
```

### Python

```python
# Default: auto-detect
runtime = RemixRuntime()

# Explicit disable
runtime = RemixRuntime(evolution=False)

# Explicit require (raises ImportError if not installed)
runtime = RemixRuntime(evolution=True)

# Check status
print(runtime.evolution_status)
# {"skill_se_kit_installed": true, "evolution_enabled": true, "backend": "...", "validator": "..."}
```

## Dependencies

- **Required**: Python >=3.9, jsonschema >=4.0
- **Optional**: `skill-se-kit` (auto-enabled when installed; install with `pip install remix[evolution]`)

## Limitations

- Scoring is heuristic-based (no LLM integration yet)
- URL sources require network access
- Compound profiles are recursive and may produce large output trees
