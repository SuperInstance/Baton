"""AutoBaton — automatic model lifecycle management.

Watches your AI system continuously, extracts lessons from operational
events, flags stale knowledge, and orchestrates generational handoffs
without manual record-keeping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from .lesson import Lesson, LessonType, ExpiryAssessment
from .validator import Validator, EnvironmentSnapshot
from .bootstrap import BootstrapGenerator
from .store import LineageStore


# ─── Protocols ────────────────────────────────────────────────────────────

class ModelRunner(Protocol):
    """Minimal interface for a model that can be tested."""

    def run(self, prompt: str) -> str: ...


# ─── Data Classes ────────────────────────────────────────────────────────

@dataclass
class HandoffReport:
    """Result of a generational handoff."""

    old_model_id: str
    new_model_id: str
    bootstrap_brief: str
    lessons_carried: int
    lessons_dropped: int
    lessons_stale: int
    survival_rate: float
    test_results: dict[str, bool] = field(default_factory=dict)
    handoff_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def summary(self) -> str:
        return (
            f"Handoff {self.old_model_id} → {self.new_model_id}: "
            f"{self.lessons_carried} carried, "
            f"{self.lessons_stale} stale, "
            f"{self.lessons_dropped} dropped "
            f"({self.survival_rate:.0%} survival)"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_model_id": self.old_model_id,
            "new_model_id": self.new_model_id,
            "bootstrap_brief": self.bootstrap_brief,
            "lessons_carried": self.lessons_carried,
            "lessons_dropped": self.lessons_dropped,
            "lessons_stale": self.lessons_stale,
            "survival_rate": self.survival_rate,
            "test_results": self.test_results,
            "handoff_at": self.handoff_at,
        }


@dataclass
class ExpiryFlag:
    """A lesson flagged as potentially stale."""

    lesson: Lesson
    reason: str
    environment_delta: dict[str, Any]


# ─── AutoBaton ──────────────────────────────────────────────────────────

class AutoBaton:
    """Automatically maintain a bootstrap brief for your AI system.

    AutoBaton sits alongside your running AI system and:
    - Records lessons from operational events as they happen
    - Periodically checks whether accumulated lessons are still valid
    - Generates bootstrap context when you upgrade to a new model
    - Executes end-to-end handoffs with testing and reporting

    Usage::

        auto = AutoBaton("my-boat")
        auto.record_lesson("quota check", "blocked 3 overages", 0.9)
        auto.check_expiry()
        report = auto.handoff("glm-5.2", "llama-3.3-70b")
        print(report.summary)
    """

    def __init__(self, system_id: str, store_dir: str | Path = "./lineage"):
        self.system_id = system_id
        self.store = LineageStore(store_dir)
        self.validator = Validator()
        self.bootstrap_gen = BootstrapGenerator()

        # State directory for system-specific data
        self.state_dir = Path(store_dir) / "auto" / system_id
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.brief = self._load_current_brief()
        self._env_history: list[dict[str, Any]] = self._load_env_history()

    # ── Lesson Recording ───────────────────────────────────────────────

    def record_lesson(
        self,
        event: str,
        outcome: str,
        confidence: float,
        *,
        source: str = "feedback",
        tags: list[str] | None = None,
        env_context: dict[str, Any] | None = None,
        lesson_type: LessonType | None = None,
    ) -> Lesson:
        """Automatically extract a lesson from a system event.

        Args:
            event: What happened (e.g. "quota check").
            outcome: What was learned (e.g. "blocked 3 overages").
            confidence: How strongly this lesson is held (0.0–1.0).
            source: Origin category (feedback, failure, pattern, experiment, fence_trigger).
            tags: Optional categorization tags.
            env_context: Environment state when the lesson was learned.
            lesson_type: Override type detection (defaults to heuristic).

        Returns:
            The recorded Lesson.
        """
        content = f"{event}: {outcome}"

        # Infer lesson type from context if not specified
        if lesson_type is None:
            lesson_type = self._infer_lesson_type(env_context or {}, source)

        lesson = Lesson(
            content=content,
            confidence=confidence,
            source=source,
            environment_context=self._snapshot_env_context(env_context),
            expiry_assessment=ExpiryAssessment.UNEVALUATED,
            lesson_type=lesson_type,
            learned_at=datetime.now(timezone.utc).isoformat(),
            tags=tags or [self.system_id],
        )

        self.brief.lessons.append(lesson)
        self._save_current_brief()
        return lesson

    def record_failure(
        self,
        what_failed: str,
        correction: str,
        severity: str = "medium",
        **kwargs: Any,
    ) -> Lesson:
        """Record a failure and its correction as a lesson."""
        base_confidence = 0.6
        if correction:
            base_confidence += 0.2
        if severity == "critical":
            base_confidence += 0.1
        return self.record_lesson(
            event=f"Failure: {what_failed}",
            outcome=correction,
            confidence=min(base_confidence, 1.0),
            source="failure",
            **kwargs,
        )

    def record_pattern(
        self,
        pattern: str,
        confidence: float = 0.8,
        **kwargs: Any,
    ) -> Lesson:
        """Record a successful pattern."""
        return self.record_lesson(
            event="Pattern observed",
            outcome=pattern,
            confidence=confidence,
            source="pattern",
            **kwargs,
        )

    # ── Expiry Checking ────────────────────────────────────────────────

    def check_expiry(
        self,
        current_env: EnvironmentSnapshot | None = None,
    ) -> list[ExpiryFlag]:
        """Flag lessons that may be stale given environment changes.

        Compares each lesson's original environment context against the
        current environment. Returns a list of flagged lessons with
        explanations of what changed.

        Args:
            current_env: Current environment snapshot. If None, attempts
                to capture one automatically.

        Returns:
            List of ExpiryFlag entries for potentially stale lessons.
        """
        if current_env is None:
            current_env = self._capture_environment()

        flags: list[ExpiryFlag] = []

        for lesson in self.brief.lessons:
            # Skip lessons already assessed
            if lesson.expiry_assessment in (
                ExpiryAssessment.EXPIRED,
                ExpiryAssessment.ACTIVE,
            ):
                # Re-check temporal lessons even if previously active
                if lesson.lesson_type != LessonType.TEMPORAL:
                    continue

            delta = self._compute_env_delta(
                lesson.environment_context, current_env
            )

            if delta:
                self.validator.validate(lesson, current_env)
                flags.append(ExpiryFlag(
                    lesson=lesson,
                    reason=self._explain_delta(delta),
                    environment_delta=delta,
                ))

        self._save_current_brief()
        self._record_env_snapshot(current_env)
        return flags

    # ── Bootstrap Generation ───────────────────────────────────────────

    def generate_bootstrap(
        self,
        new_model_id: str,
        current_env: EnvironmentSnapshot | None = None,
    ) -> str:
        """Generate the bootstrap context for a model upgrade.

        Validates all lessons against the current environment and
        produces a structured bootstrap brief suitable for the new
        model's system prompt.

        Args:
            new_model_id: The model that will receive this bootstrap.
            current_env: Current environment snapshot.

        Returns:
            A structured bootstrap brief string.
        """
        if current_env is None:
            current_env = self._capture_environment()

        from . import ValidatedBrief

        validated = ValidatedBrief(
            handoff=self.brief,
            active_lessons=[],
            stale_lessons=[],
            deprecated_lessons=[],
            environment=current_env,
        )

        active, stale, deprecated = self.validator.validate_batch(
            self.brief.lessons, current_env
        )
        validated.active_lessons = active
        validated.stale_lessons = stale
        validated.deprecated_lessons = deprecated

        brief = self.bootstrap_gen.generate(validated)
        # Tag with target model
        brief = brief.replace(
            "# Bootstrap Brief — Generational Handoff",
            f"# Bootstrap Brief — Generational Handoff\nTarget: {new_model_id}",
        )
        return brief

    # ── Full Handoff ───────────────────────────────────────────────────

    def handoff(
        self,
        old_model: str | ModelRunner,
        new_model: str | ModelRunner,
        *,
        test_prompts: list[str] | None = None,
        current_env: EnvironmentSnapshot | None = None,
    ) -> HandoffReport:
        """Execute the generational handoff.

        This is the full baton pass:
        1. Validate all lessons against the current environment
        2. Generate the bootstrap brief for the new model
        3. Test the new model with the bootstrap (if runners provided)
        4. Report what carried and what didn't

        Args:
            old_model: Model ID string or a ModelRunner for the old model.
            new_model: Model ID string or a ModelRunner for the new model.
            test_prompts: Optional prompts to test the new model with.
            current_env: Environment snapshot override.

        Returns:
            A HandoffReport with full details.
        """
        old_id = old_model if isinstance(old_model, str) else getattr(
            old_model, "model_id", "old-model"
        )
        new_id = new_model if isinstance(new_model, str) else getattr(
            new_model, "model_id", "new-model"
        )

        if current_env is None:
            current_env = self._capture_environment()

        # 1. Validate lessons
        from . import ValidatedBrief

        active, stale, deprecated = self.validator.validate_batch(
            self.brief.lessons, current_env
        )

        validated = ValidatedBrief(
            handoff=self.brief,
            active_lessons=active,
            stale_lessons=stale,
            deprecated_lessons=deprecated,
            environment=current_env,
        )

        # 2. Generate bootstrap
        bootstrap = self.generate_bootstrap(new_id, current_env)

        # 3. Test if we have runners
        test_results: dict[str, bool] = {}
        if not isinstance(new_model, str):
            runner = new_model
            prompts = test_prompts or self._default_test_prompts()
            for prompt in prompts:
                try:
                    response = runner.run(prompt)
                    test_results[prompt] = bool(response) and len(response) > 0
                except Exception:
                    test_results[prompt] = False

        # 4. Build report
        total = len(self.brief.lessons)
        carried = len(active)
        dropped = len(deprecated)
        stale_count = len(stale)
        survival = carried / total if total > 0 else 1.0

        report = HandoffReport(
            old_model_id=old_id,
            new_model_id=new_id,
            bootstrap_brief=bootstrap,
            lessons_carried=carried,
            lessons_dropped=dropped,
            lessons_stale=stale_count,
            survival_rate=survival,
            test_results=test_results,
        )

        # Save handoff record
        self._save_handoff_report(report)

        return report

    # ── Persistence ────────────────────────────────────────────────────

    def _load_current_brief(self) -> Any:
        """Load the current accumulated brief from disk."""
        from . import HandoffBrief

        path = self.state_dir / "current_brief.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return HandoffBrief.from_dict(data)

        # Initialize new brief
        return HandoffBrief(
            id=f"auto-{self.system_id}-{uuid4().hex[:8]}",
            model_id=self.system_id,
            generation=1,
            lessons=[],
        )

    def _save_current_brief(self) -> None:
        """Persist the current brief to disk."""
        path = self.state_dir / "current_brief.json"
        path.write_text(
            json.dumps(self.brief.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _save_handoff_report(self, report: HandoffReport) -> None:
        """Save a handoff report for audit trail."""
        reports_dir = self.state_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        filename = f"handoff_{report.old_model_id}_to_{report.new_model_id}.json"
        path = reports_dir / filename
        path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_env_history(self) -> list[dict[str, Any]]:
        """Load environment snapshot history."""
        path = self.state_dir / "env_history.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return []

    def _record_env_snapshot(self, env: EnvironmentSnapshot) -> None:
        """Record an environment snapshot for tracking changes over time."""
        self._env_history.append(env.to_dict())
        # Keep last 100 snapshots
        self._env_history = self._env_history[-100:]
        path = self.state_dir / "env_history.json"
        path.write_text(
            json.dumps(self._env_history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Environment Helpers ─────────────────────────────────────────────

    def _capture_environment(self) -> EnvironmentSnapshot:
        """Capture the current environment automatically.

        Override this in subclasses for system-specific detection.
        """
        env = EnvironmentSnapshot()
        env.model_family = self.system_id
        return env

    def _snapshot_env_context(
        self, override: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Capture current environment context for a lesson."""
        ctx: dict[str, Any] = {"recorded_by": self.system_id}
        if override:
            ctx.update(override)
        return ctx

    @staticmethod
    def _compute_env_delta(
        lesson_ctx: dict[str, Any],
        env: EnvironmentSnapshot,
    ) -> dict[str, Any]:
        """Compute what changed between a lesson's context and now."""
        delta: dict[str, Any] = {}

        # Runtime version
        lesson_runtime = lesson_ctx.get("runtime", {}).get("version", "")
        if lesson_runtime and env.runtime_version and lesson_runtime != env.runtime_version:
            delta["runtime"] = {"from": lesson_runtime, "to": env.runtime_version}

        # Conservation version
        lesson_cons = lesson_ctx.get("conservation_version", "")
        if lesson_cons and env.conservation_version and lesson_cons != env.conservation_version:
            delta["conservation_version"] = {"from": lesson_cons, "to": env.conservation_version}

        # Task domain
        lesson_domain = lesson_ctx.get("task_domain", "")
        if lesson_domain and env.task_domain and lesson_domain != env.task_domain:
            delta["task_domain"] = {"from": lesson_domain, "to": env.task_domain}

        # API versions
        lesson_apis = lesson_ctx.get("api_versions", {})
        for api, version in lesson_apis.items():
            if api in env.api_versions and env.api_versions[api] != version:
                delta.setdefault("api_versions", {})[api] = {
                    "from": version,
                    "to": env.api_versions[api],
                }

        # Rate limits
        lesson_limits = lesson_ctx.get("rate_limits", {})
        for service, limit in lesson_limits.items():
            if service in env.rate_limits and env.rate_limits[service] != limit:
                delta.setdefault("rate_limits", {})[service] = {
                    "from": limit,
                    "to": env.rate_limits[service],
                }

        return delta

    @staticmethod
    def _explain_delta(delta: dict[str, Any]) -> str:
        """Human-readable explanation of what changed."""
        parts: list[str] = []
        for key, change in delta.items():
            if isinstance(change, dict) and "from" in change:
                parts.append(f"{key}: {change['from']} → {change['to']}")
            else:
                parts.append(f"{key} changed")
        return "; ".join(parts)

    @staticmethod
    def _infer_lesson_type(
        context: dict[str, Any], source: str
    ) -> LessonType:
        """Heuristic type inference from context and source."""
        if source == "fence_trigger":
            return LessonType.TIMELESS
        # Failures are environment-specific by default
        if source == "failure":
            return LessonType.TEMPORAL
        temporal_keys = {
            "api_version", "rate_limit", "model_version",
            "sdk_version", "runtime", "conservation_version",
        }
        if any(k in context for k in temporal_keys):
            return LessonType.TEMPORAL
        return LessonType.TIMELESS

    @staticmethod
    def _default_test_prompts() -> list[str]:
        """Default prompts to test a new model during handoff."""
        return [
            "Summarize the key lessons from your bootstrap brief.",
            "What conservation fences must you respect?",
            "Describe a failure mode from the previous generation and how to avoid it.",
        ]

    # ── Stats ──────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Quick statistics about the system's accumulated wisdom."""
        lessons = self.brief.lessons
        by_source: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_assessment: dict[str, int] = {}

        for lesson in lessons:
            by_source[lesson.source] = by_source.get(lesson.source, 0) + 1
            by_type[lesson.lesson_type.value] = by_type.get(lesson.lesson_type.value, 0) + 1
            by_assessment[lesson.expiry_assessment.value] = (
                by_assessment.get(lesson.expiry_assessment.value, 0) + 1
            )

        avg_confidence = (
            sum(l.confidence for l in lessons) / len(lessons) if lessons else 0.0
        )

        return {
            "system_id": self.system_id,
            "total_lessons": len(lessons),
            "by_source": by_source,
            "by_type": by_type,
            "by_assessment": by_assessment,
            "avg_confidence": round(avg_confidence, 3),
            "env_snapshots": len(self._env_history),
        }
