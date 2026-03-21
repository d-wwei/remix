# Remix

`Remix` is an artifact reconstruction and synthesis system that can target
skills, protocols, modules, features, products, and compound bundles.

It is independent from `Skill-SE-Kit`, but integrates `Skill-SE-Kit` when it
wants self-evolution, audit, provenance, verification, and governed handoff
capabilities.

## Relationship To Other Repositories

- `skill-evolution-protocol`: shared schemas and interoperability contract
- `skill-se-kit`: self-evolving runtime substrate used by Remix when appropriate
- `agent-skill-governor`: governance layer that can invoke Remix and review
  governed skill outputs

## Package Layout

```text
remix/
  src/remix/
  tests/
  docs/
  examples/
```

## Runtime Entry Point

The main runtime entry point is `remix.runtime.RemixRuntime`.

## Running Tests

Install `Skill-SE-Kit` first, then run:

```bash
python3 -m pip install ../skill-se-kit
python3 -m pip install .
python3 -m unittest discover -s tests -p 'test_*.py'
```
