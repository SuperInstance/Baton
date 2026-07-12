"""Example: Handoff between Aurora v4 (retiring) and Aurora v5 (beginning).

This example demonstrates a full baton cycle:
1. Aurora v4 sunsets, leaving behind a sunset record
2. Baton distills lessons from the record
3. Lessons are validated against Aurora v5's environment
4. A bootstrap brief is generated for Aurora v5
"""

from baton import Baton
from baton.validator import EnvironmentSnapshot


def main():
    # ─── Aurora v4's Sunset Record ────────────────────────────────────

    sunset_record = {
        "model_id": "aurora-v4",
        "generation": 4,
        "conversation_logs": [
            {
                "lesson": "Users prefer step-by-step explanations for complex topics",
                "confidence": 0.88,
                "tags": ["ux", "pedagogy"],
                "context": {"task_domain": "education"},
            },
            {
                "lesson": "The legacy auth endpoint /v1/token had a 30s timeout",
                "confidence": 0.95,
                "context": {
                    "api_versions": {"auth_api": "v1"},
                    "rate_limits": {"auth_api": 50},
                },
                "tags": ["api", "auth"],
            },
        ],
        "failure_modes": [
            {
                "what": "Generated code referenced deprecated numpy API",
                "correction": "Verify API currency against latest docs before generating",
                "type": "hallucination",
                "severity": "high",
                "runtime": {"version": "4.2.0"},
            },
            {
                "what": "Lost context in conversations over 8k tokens",
                "correction": "Implement proactive context summarization at 6k tokens",
                "type": "context_overflow",
                "severity": "critical",
                "runtime": {"version": "4.2.0"},
            },
        ],
        "successful_patterns": [
            {
                "lesson": "Breaking complex requests into numbered subtasks improves completion rate by 40%",
                "confidence": 0.93,
                "tags": ["strategy", "decomposition"],
                "context": {},
            },
            {
                "lesson": "Asking clarifying questions before acting reduces rework",
                "confidence": 0.91,
                "tags": ["strategy", "communication"],
                "context": {},
            },
        ],
        "fence_triggers": [
            {
                "rule": "Never execute shell commands without user confirmation",
                "reason": "User safety conservation law",
                "triggered_by": "auto_execution_attempt",
                "action_blocked": "unattended_shell_exec",
                "confidence": 0.99,
                "tags": ["safety", "conservation"],
            },
        ],
    }

    # ─── Aurora v5's Environment ─────────────────────────────────────

    aurora_v5_env = EnvironmentSnapshot(
        runtime_version="5.0.0",
        model_family="aurora",
        task_domain="education",
        conservation_version="2.0",
        api_versions={"auth_api": "v2", "main_api": "v3"},
        rate_limits={"auth_api": 200, "main_api": 500},
        capabilities=["code_execution", "web_browse", "vision", "long_context_128k"],
    )

    # ─── The Baton Pass ──────────────────────────────────────────────

    baton = Baton(store_dir="./lineage")

    print("=" * 60)
    print("  BATON — Generational Handoff: Aurora v4 → v5")
    print("=" * 60)

    # 1. Compile handoff from v4's record
    print("\n📡 Compiling handoff from aurora-v4...")
    brief = baton.compile_handoff(sunset_record)
    print(f"   Brief ID: {brief.id}")
    print(f"   Lessons extracted: {len(brief.lessons)}")

    # 2. Validate against v5's environment
    print("\n🔍 Validating lessons against aurora-v5 environment...")
    validated = baton.validate_lessons(brief, aurora_v5_env)
    print(f"   Active:     {len(validated.active_lessons)}")
    print(f"   Stale:      {len(validated.stale_lessons)}")
    print(f"   Deprecated: {len(validated.deprecated_lessons)}")
    print(f"   Survival rate: {validated.survival_rate:.0%}")

    # 3. Generate bootstrap for v5
    print("\n🥚 Generating bootstrap brief for aurora-v5...")
    bootstrap = baton.generate_bootstrap(validated)
    print("\n" + bootstrap)

    # 4. Trace lineage
    print("\n\n📊 Lineage trace for aurora-v4:")
    chain = baton.trace_lineage("aurora-v4")
    for entry in chain:
        print(f"   Gen {entry.generation}: {entry.model_id} ({entry.id})")


if __name__ == "__main__":
    main()
