"""Baton CLI — command-line interface for model lifecycle management.

Usage::

    baton init --system-id my-boat
    baton record --event "quota check" --outcome "blocked 3 overages" --confidence 0.9
    baton record-failure --what "timeout" --correction "add retry" --severity high
    baton record-pattern --pattern "batch requests reduce latency" --confidence 0.85
    baton check-expiry
    baton bootstrap --new-model llama-3.3-70b
    baton handoff --old glm-5.2 --new llama-3.3-70b
    baton stats
    baton list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .auto import AutoBaton
from .lesson import LessonType, ExpiryAssessment
from .validator import EnvironmentSnapshot


def _print_lesson(lesson) -> None:
    """Print a single lesson in a readable format."""
    conf_bar = "▓" * int(lesson.confidence * 5)
    conf_bar += "░" * (5 - len(conf_bar))
    tags = f" [{', '.join(lesson.tags)}]" if lesson.tags else ""
    print(
        f"  [{lesson.lesson_type.value:>9}] {lesson.content}{tags}\n"
        f"            confidence: {lesson.confidence:.0%} {conf_bar} | "
        f"source: {lesson.source} | "
        f"assessment: {lesson.expiry_assessment.value}"
    )


def _get_store_dir(args) -> str:
    return getattr(args, "store_dir", "./lineage")


def cmd_init(args) -> int:
    """Initialize a new baton system."""
    store = _get_store_dir(args)
    auto = AutoBaton(args.system_id, store_dir=store)
    print(f"✓ Initialized baton system: {args.system_id}")
    print(f"  Store: {Path(store).resolve()}")
    print(f"  Baton ID: {auto.brief.id}")
    return 0


def cmd_record(args) -> int:
    """Record a lesson from an operational event."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    lesson = auto.record_lesson(
        event=args.event,
        outcome=args.outcome,
        confidence=args.confidence,
        source=args.source,
        tags=args.tags.split(",") if args.tags else None,
    )
    print(f"✓ Recorded lesson:")
    _print_lesson(lesson)
    return 0


def cmd_record_failure(args) -> int:
    """Record a failure and its correction."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    lesson = auto.record_failure(
        what_failed=args.what,
        correction=args.correction,
        severity=args.severity,
    )
    print(f"✓ Recorded failure lesson:")
    _print_lesson(lesson)
    return 0


def cmd_record_pattern(args) -> int:
    """Record a successful pattern."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    lesson = auto.record_pattern(
        pattern=args.pattern,
        confidence=args.confidence,
    )
    print(f"✓ Recorded pattern:")
    _print_lesson(lesson)
    return 0


def cmd_check_expiry(args) -> int:
    """Check lessons for expiry."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))

    env = None
    if args.runtime or args.domain or args.conservation:
        env = EnvironmentSnapshot(
            runtime_version=args.runtime or "",
            task_domain=args.domain or "",
            conservation_version=args.conservation or "",
        )

    flags = auto.check_expiry(current_env=env)

    if not flags:
        print("✓ All lessons are current. No expiry flags.")
        return 0

    print(f"⚠ {len(flags)} lesson(s) flagged for review:\n")
    for flag in flags:
        print(f"  ⚠ {flag.lesson.content}")
        print(f"    Reason: {flag.reason}")
        print(f"    Assessment: {flag.lesson.expiry_assessment.value}")
        print()
    return 0


def cmd_bootstrap(args) -> int:
    """Generate bootstrap context for a new model."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))

    env = None
    if args.runtime or args.domain or args.conservation:
        env = EnvironmentSnapshot(
            runtime_version=args.runtime or "",
            task_domain=args.domain or "",
            conservation_version=args.conservation or "",
        )

    bootstrap = auto.generate_bootstrap(args.new_model, current_env=env)

    if args.output:
        Path(args.output).write_text(bootstrap, encoding="utf-8")
        print(f"✓ Bootstrap brief written to {args.output}")
    else:
        print(bootstrap)
    return 0


def cmd_handoff(args) -> int:
    """Execute a full generational handoff."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))

    env = None
    if args.runtime or args.domain or args.conservation:
        env = EnvironmentSnapshot(
            runtime_version=args.runtime or "",
            task_domain=args.domain or "",
            conservation_version=args.conservation or "",
        )

    report = auto.handoff(
        old_model=args.old,
        new_model=args.new,
        current_env=env,
    )

    print(f"\n{'═' * 60}")
    print(f"  GENERATIONAL HANDOFF COMPLETE")
    print(f"{'═' * 60}")
    print(f"  {report.old_model_id} → {report.new_model_id}")
    print(f"{'─' * 60}")
    print(f"  Lessons carried:   {report.lessons_carried}")
    print(f"  Lessons stale:     {report.lessons_stale}")
    print(f"  Lessons dropped:   {report.lessons_dropped}")
    print(f"  Survival rate:     {report.survival_rate:.0%}")
    print(f"  Handoff at:        {report.handoff_at}")

    if report.test_results:
        print(f"{'─' * 60}")
        print(f"  Test Results:")
        for prompt, passed in report.test_results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"    {status}: {prompt[:60]}")

    if args.save_bootstrap:
        Path(args.save_bootstrap).write_text(
            report.bootstrap_brief, encoding="utf-8"
        )
        print(f"{'─' * 60}")
        print(f"  Bootstrap saved: {args.save_bootstrap}")

    print(f"{'═' * 60}\n")
    return 0


def cmd_stats(args) -> int:
    """Show statistics about accumulated wisdom."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    stats = auto.stats

    print(f"\n  System: {stats['system_id']}")
    print(f"  Total lessons: {stats['total_lessons']}")
    print(f"  Avg confidence: {stats['avg_confidence']:.0%}")
    print(f"  Env snapshots: {stats['env_snapshots']}")

    if stats["by_source"]:
        print(f"\n  By source:")
        for source, count in sorted(stats["by_source"].items(), key=lambda x: -x[1]):
            print(f"    {source:>16}: {count}")

    if stats["by_type"]:
        print(f"\n  By type:")
        for ltype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            print(f"    {ltype:>16}: {count}")

    if stats["by_assessment"]:
        print(f"\n  By assessment:")
        for assessment, count in sorted(stats["by_assessment"].items(), key=lambda x: -x[1]):
            print(f"    {assessment:>16}: {count}")
    print()
    return 0


def cmd_list(args) -> int:
    """List all recorded lessons."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    lessons = auto.brief.lessons

    if not lessons:
        print("  No lessons recorded yet.")
        return 0

    print(f"\n  {len(lessons)} lesson(s) for {args.system_id}:\n")
    for lesson in lessons:
        _print_lesson(lesson)
    print()
    return 0


def cmd_show(args) -> int:
    """Show details of the current brief."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    brief = auto.brief

    print(f"\n  Baton ID:     {brief.id}")
    print(f"  System:       {brief.model_id}")
    print(f"  Generation:   {brief.generation}")
    print(f"  Compiled at:  {brief.compiled_at}")
    print(f"  Lessons:      {len(brief.lessons)}")
    if brief.parent_brief_id:
        print(f"  Parent:       {brief.parent_brief_id}")
    print()
    return 0


def cmd_export(args) -> int:
    """Export the current brief as JSON."""
    auto = AutoBaton(args.system_id, store_dir=_get_store_dir(args))
    data = auto.brief.to_dict()

    if args.output:
        Path(args.output).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"✓ Exported to {args.output}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


# ─── Parser ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="baton",
        description=(
            "Baton — Generational handoff for model lifecycle.\n"
            "Carries distilled wisdom from one model generation to the next."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "--store-dir", default="./lineage",
        help="Directory for lineage storage (default: ./lineage)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new baton system")
    p_init.add_argument("--system-id", required=True, help="Unique system identifier")
    p_init.set_defaults(func=cmd_init)

    # record
    p_record = subparsers.add_parser("record", help="Record a lesson from an event")
    p_record.add_argument("--system-id", required=True, help="System identifier")
    p_record.add_argument("--event", required=True, help="What happened")
    p_record.add_argument("--outcome", required=True, help="What was learned")
    p_record.add_argument("--confidence", type=float, default=0.7, help="Confidence 0.0-1.0")
    p_record.add_argument("--source", default="feedback", help="Source category")
    p_record.add_argument("--tags", default=None, help="Comma-separated tags")
    p_record.set_defaults(func=cmd_record)

    # record-failure
    p_fail = subparsers.add_parser("record-failure", help="Record a failure and correction")
    p_fail.add_argument("--system-id", required=True, help="System identifier")
    p_fail.add_argument("--what", required=True, help="What failed")
    p_fail.add_argument("--correction", required=True, help="How to fix it")
    p_fail.add_argument("--severity", default="medium", choices=["low", "medium", "high", "critical"])
    p_fail.set_defaults(func=cmd_record_failure)

    # record-pattern
    p_pat = subparsers.add_parser("record-pattern", help="Record a successful pattern")
    p_pat.add_argument("--system-id", required=True, help="System identifier")
    p_pat.add_argument("--pattern", required=True, help="The pattern description")
    p_pat.add_argument("--confidence", type=float, default=0.8, help="Confidence 0.0-1.0")
    p_pat.set_defaults(func=cmd_record_pattern)

    # check-expiry
    p_expiry = subparsers.add_parser("check-expiry", help="Flag potentially stale lessons")
    p_expiry.add_argument("--system-id", required=True, help="System identifier")
    p_expiry.add_argument("--runtime", default=None, help="Current runtime version")
    p_expiry.add_argument("--domain", default=None, help="Current task domain")
    p_expiry.add_argument("--conservation", default=None, help="Conservation law version")
    p_expiry.set_defaults(func=cmd_check_expiry)

    # bootstrap
    p_boot = subparsers.add_parser("bootstrap", help="Generate bootstrap context for new model")
    p_boot.add_argument("--system-id", required=True, help="System identifier")
    p_boot.add_argument("--new-model", required=True, help="New model identifier")
    p_boot.add_argument("--runtime", default=None, help="Current runtime version")
    p_boot.add_argument("--domain", default=None, help="Current task domain")
    p_boot.add_argument("--conservation", default=None, help="Conservation law version")
    p_boot.add_argument("--output", "-o", default=None, help="Write to file instead of stdout")
    p_boot.set_defaults(func=cmd_bootstrap)

    # handoff
    p_hand = subparsers.add_parser("handoff", help="Execute full generational handoff")
    p_hand.add_argument("--system-id", required=True, help="System identifier")
    p_hand.add_argument("--old", required=True, help="Old model identifier")
    p_hand.add_argument("--new", required=True, help="New model identifier")
    p_hand.add_argument("--runtime", default=None, help="Current runtime version")
    p_hand.add_argument("--domain", default=None, help="Current task domain")
    p_hand.add_argument("--conservation", default=None, help="Conservation law version")
    p_hand.add_argument("--save-bootstrap", default=None, help="Save bootstrap brief to file")
    p_hand.set_defaults(func=cmd_handoff)

    # stats
    p_stats = subparsers.add_parser("stats", help="Show system statistics")
    p_stats.add_argument("--system-id", required=True, help="System identifier")
    p_stats.set_defaults(func=cmd_stats)

    # list
    p_list = subparsers.add_parser("list", help="List all recorded lessons")
    p_list.add_argument("--system-id", required=True, help="System identifier")
    p_list.set_defaults(func=cmd_list)

    # show
    p_show = subparsers.add_parser("show", help="Show current brief details")
    p_show.add_argument("--system-id", required=True, help="System identifier")
    p_show.set_defaults(func=cmd_show)

    # export
    p_export = subparsers.add_parser("export", help="Export current brief as JSON")
    p_export.add_argument("--system-id", required=True, help="System identifier")
    p_export.add_argument("--output", "-o", default=None, help="Write to file")
    p_export.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
