# Remix

[中文说明](README.zh-CN.md)

`Remix` is an artifact reconstruction and synthesis system.
It can analyze, compare, restructure, and rebuild artifacts such as skills, protocols, modules, features, products, and compound bundles.

`Remix` is an independent product.
When a remix workflow needs self-evolution, audit, provenance, verification, or governed handoff, it integrates `Skill-SE-Kit` instead of embedding those responsibilities directly.

## Core Workflow

- collect a brief and target constraints
- ingest and normalize source artifacts
- analyze sources in parallel
- compare strengths, weaknesses, and structural patterns
- synthesize strategy options
- build the selected output artifact
- verify, package, and hand off results

## Current Implementation Focus

The current codebase provides the runtime foundation for:

- artifact source intake
- planning and comparison scaffolding
- runtime orchestration
- build and verification helpers
- integration with `Skill-SE-Kit` for governed or self-evolving flows

## Repository Layout

```text
remix/
  README.md
  README.zh-CN.md
  src/remix/
  tests/
  docs/
  examples/
```

## Runtime Entry Point

The main runtime entry point is `remix.runtime.RemixRuntime`.

## Quick Start

Install `Skill-SE-Kit` first, then run:

```bash
python3 -m pip install ../skill-se-kit
python3 -m pip install .
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Relationship To Other Repositories

- [Skill Evolution Protocol](https://github.com/d-wwei/skill-evolution-protocol): shared schemas and interoperability contract
- [Skill-SE-Kit](https://github.com/d-wwei/skill-se-kit): self-evolving runtime substrate used by Remix when needed
- [Agent Skill Governor](https://github.com/d-wwei/agent-skill-governor): governance layer that can invoke Remix and review governed outputs

