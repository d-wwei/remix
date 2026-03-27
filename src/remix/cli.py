from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_json_arg(value: str) -> object:
    """Parse a CLI argument as inline JSON or a file path."""
    stripped = value.strip()
    if stripped.startswith(("{", "[")):
        return json.loads(stripped)
    path = Path(stripped)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"File not found: {stripped}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_sources_arg(value: str) -> list:
    """Parse the --sources argument.

    Accepts:
    - Inline JSON (object or array)
    - A path to a JSON file
    - A bare GitHub repository URL (``https://github.com/owner/repo``),
      which is automatically wrapped into
      ``[{"kind": "github_repo", "url": "..."}]``
    """
    from remix.sources import is_github_repo_url

    stripped = value.strip()

    # Fast path: bare GitHub repo URL on the command line.
    if is_github_repo_url(stripped):
        return [{"kind": "github_repo", "url": stripped}]

    # Delegate to the standard JSON loader.
    result = _load_json_arg(value)

    # Wrap a single source dict in a list for convenience.
    if isinstance(result, dict):
        return [result]
    return result


def _resolve_evolution(args: argparse.Namespace) -> bool | object:
    """Resolve evolution flag: default (auto), or explicit disable."""
    from remix.runtime import _SENTINEL
    if getattr(args, "no_evolution", False):
        return False
    return _SENTINEL  # auto-detect


def _make_runtime(args: argparse.Namespace, **kwargs):
    from remix.runtime import RemixRuntime
    evolution = _resolve_evolution(args)
    return RemixRuntime(evolution=evolution, **kwargs)


def _cmd_run(args: argparse.Namespace) -> None:
    runtime = _make_runtime(args, output_root=args.output)
    summary = runtime.run(
        brief=_load_json_arg(args.brief),
        sources=_load_sources_arg(args.sources),
        selected_strategy_id=args.strategy,
    )
    summary["evolution"] = runtime.evolution_status
    json.dump(summary, sys.stdout, indent=2)
    print()


def _cmd_analyze(args: argparse.Namespace) -> None:
    """Run only the intake + analysis phase. Outputs per-source scores."""
    runtime = _make_runtime(args)
    brief = _load_json_arg(args.brief)
    sources = _load_sources_arg(args.sources)
    target_profile = runtime.profile_registry.resolve(brief)
    normalized = runtime.source_adapter.normalize_sources(sources, brief)
    reports = runtime.source_analyzer.analyze_sources(
        normalized, brief=brief, target_profile=target_profile,
    )
    output = {
        "target_profile": target_profile["profile_id"],
        "source_count": len(reports),
        "evolution": runtime.evolution_status,
        "reports": [
            {
                "source_id": r["source_id"],
                "strengths": r["strengths"],
                "weaknesses": r["weaknesses"],
                "scores": r["scores"],
            }
            for r in reports
        ],
    }
    json.dump(output, sys.stdout, indent=2)
    print()


def _cmd_compare(args: argparse.Namespace) -> None:
    """Run intake + analysis + comparison. Outputs rankings and strategies."""
    runtime = _make_runtime(args)
    brief = _load_json_arg(args.brief)
    sources = _load_sources_arg(args.sources)
    target_profile = runtime.profile_registry.resolve(brief)
    normalized = runtime.source_adapter.normalize_sources(sources, brief)
    reports = runtime.source_analyzer.analyze_sources(
        normalized, brief=brief, target_profile=target_profile,
    )
    comparison = runtime.comparison_engine.build(
        reports, normalized, brief=brief, target_profile=target_profile,
    )
    strategies = runtime.strategy_synthesizer.synthesize(
        comparison, reports, normalized, brief=brief, target_profile=target_profile,
    )
    output = {
        "target_profile": target_profile["profile_id"],
        "evolution": runtime.evolution_status,
        "rankings": comparison["source_rankings"],
        "complementarity": comparison["complementarity"],
        "strategies": [
            {
                "strategy_id": s["strategy_id"],
                "name": s["name"],
                "strategy_score": s["strategy_score"],
                "source_ids": s["source_ids"],
                "preserve": s["preserve"],
                "risks": s["risks"],
            }
            for s in strategies
        ],
        "comparison_matrix": comparison["comparison_matrix_markdown"],
    }
    json.dump(output, sys.stdout, indent=2)
    print()


def _cmd_profiles(args: argparse.Namespace) -> None:
    runtime = _make_runtime(args)
    profiles = runtime.list_profiles()
    json.dump(profiles, sys.stdout, indent=2)
    print()


def _add_evolution_flag(parser: argparse.ArgumentParser) -> None:
    """Add --no-evolution flag to a subparser."""
    parser.add_argument(
        "--no-evolution",
        action="store_true",
        default=False,
        help="Disable skill-se-kit integration even if installed (default: auto-detect and enable)",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="remix", description="Artifact reconstruction and synthesis tool")
    sub = parser.add_subparsers(dest="command")

    # --- run ---
    run_parser = sub.add_parser("run", help="Run the full remix pipeline")
    run_parser.add_argument("--brief", required=True, help="Brief as inline JSON or path to JSON file")
    run_parser.add_argument("--sources", required=True, help="Sources as inline JSON, path to JSON file, or a GitHub repo URL")
    run_parser.add_argument("--strategy", default=None, help="Strategy ID to select (auto-selects best if omitted)")
    run_parser.add_argument("--output", default=None, help="Output root directory (default: .remix/)")
    _add_evolution_flag(run_parser)

    # --- analyze ---
    analyze_parser = sub.add_parser("analyze", help="Analyze sources without building (scores only)")
    analyze_parser.add_argument("--brief", required=True, help="Brief as inline JSON or path to JSON file")
    analyze_parser.add_argument("--sources", required=True, help="Sources as inline JSON, path to JSON file, or a GitHub repo URL")
    _add_evolution_flag(analyze_parser)

    # --- compare ---
    compare_parser = sub.add_parser("compare", help="Analyze and compare sources (rankings + strategies)")
    compare_parser.add_argument("--brief", required=True, help="Brief as inline JSON or path to JSON file")
    compare_parser.add_argument("--sources", required=True, help="Sources as inline JSON, path to JSON file, or a GitHub repo URL")
    _add_evolution_flag(compare_parser)

    # --- profiles ---
    profiles_parser = sub.add_parser("profiles", help="List available target profiles")
    _add_evolution_flag(profiles_parser)

    args = parser.parse_args(argv)
    if args.command == "run":
        _cmd_run(args)
    elif args.command == "analyze":
        _cmd_analyze(args)
    elif args.command == "compare":
        _cmd_compare(args)
    elif args.command == "profiles":
        _cmd_profiles(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
