# Remix

[中文说明](README.zh-CN.md)

`Remix` is a universal artifact reconstruction and synthesis tool.
It analyzes, compares, and rebuilds artifacts — skills, protocols, modules, features, products, and compound bundles.

Remix is a **standalone tool**. It works on its own with zero external dependencies beyond Python and jsonschema.
When you want self-evolution or governance integration, install the optional `skill-se-kit` plugin.

## Quick Start

```bash
pip install .
```

Analyze sources (scores only, no build):

```bash
remix analyze \
  --brief '{"target_profile":"skill","target_job":"evaluate sources"}' \
  --sources '[{"kind":"file","path":"./source.md"}]'
```

Compare sources (rankings + strategy options):

```bash
remix compare \
  --brief '{"target_profile":"skill","target_job":"pick the best source"}' \
  --sources '[{"kind":"file","path":"./a.md"},{"kind":"file","path":"./b.md"}]'
```

Run the full pipeline (analyze → compare → build → verify):

```bash
remix run \
  --brief '{"target_profile":"skill","target_job":"build a code review skill"}' \
  --sources '[{"kind":"file","path":"./my-skill.md"}]'
```

List available target profiles:

```bash
remix profiles
```

## Core Workflow

1. **Intake** — collect a brief (what you want) and sources (what you have)
2. **Normalize** — convert diverse source formats into canonical representations
3. **Analyze** — score each source across configurable dimensions (0–5 scale)
4. **Compare** — rank sources, apply hard gates, find complementary pairs
5. **Synthesize** — generate 2–3 strategy options (conservative, balanced, forward-port)
6. **Build** — materialize the selected output artifact
7. **Verify** — run profile-specific checks
8. **Audit & Handoff** — produce provenance trail and release metadata

## Target Profiles

| Profile | Outputs | Use Case |
|---------|---------|----------|
| `skill` | manifest.json, SKILL.md, tests.md | Agent skills |
| `protocol` | schema.json, examples, compatibility matrix | Interop contracts |
| `module` | package layout, source, tests | Reusable code packages |
| `feature` | spec, rollout plan, acceptance criteria | Product features |
| `product` | PRD, roadmap, capability map | Product definitions |
| `compound` | Recursive bundle of above | Multi-artifact systems |

## Configurable Scoring

Scoring dimensions and weights are configurable per-run via the brief:

```json
{
  "target_profile": "skill",
  "target_job": "...",
  "scoring_overrides": {
    "task_fit": { "weight": 1.5 },
    "testability": { "weight": 0.5 },
    "custom_dimension": { "weight": 1.0, "score": 4.2 }
  }
}
```

Each target profile ships with sensible default weights. Override only what you need.

## Extension Points

| Extension | Purpose | Required? |
|-----------|---------|-----------|
| `Analyzer` | Replace heuristic scoring with LLM-backed or custom analysis | No (heuristic default) |
| `Validator` | Custom manifest/proposal validation | No (null default) |
| `EvolutionBackend` | Self-evolution experience recording | No (null default) |

All are Python `Protocol` classes — implement and inject at runtime:

```python
from remix import RemixRuntime

runtime = RemixRuntime(
    analyzer=my_llm_analyzer,
    validator=my_validator,
    evolution_backend=my_backend,
)
```

## Optional: Skill-SE-Kit Integration

If you want Remix to record experience and evolve over time:

```bash
pip install ".[evolution]"
```

```python
from remix import from_skill_runtime

runtime = from_skill_runtime(
    skill_root="/path/to/skill",
    protocol_root="/path/to/protocol",
)
```

This is **optional**. Remix works fully without it.

## Repository Layout

```text
remix/
  SKILL.md           — skill description for agent discovery
  manifest.json      — machine-readable skill metadata
  README.md
  README.zh-CN.md
  pyproject.toml
  src/remix/         — core implementation
  tests/             — test suite
```

## Related Projects

- [Skill-SE-Kit](https://github.com/d-wwei/skill-se-kit): optional self-evolution plugin
- [Agent Skill Governor](https://github.com/d-wwei/agent-skill-governor): governance layer that can invoke Remix
