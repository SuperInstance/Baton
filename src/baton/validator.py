"""Validator — check lessons against the current environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .lesson import Lesson, LessonType, ExpiryAssessment


@dataclass
class EnvironmentSnapshot:
    """Snapshot of the current runtime environment.

    Used to validate whether lessons from a previous generation
    still apply.
    """

    runtime_version: str = ""
    model_family: str = ""
    task_domain: str = ""
    conservation_version: str = ""
    api_versions: dict[str, str] = field(default_factory=dict)
    rate_limits: dict[str, int] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    snapshot_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": self.runtime_version,
            "model_family": self.model_family,
            "task_domain": self.task_domain,
            "conservation_version": self.conservation_version,
            "api_versions": self.api_versions,
            "rate_limits": self.rate_limits,
            "capabilities": self.capabilities,
            "snapshot_at": self.snapshot_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentSnapshot:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class Validator:
    """Validates lessons against the current environment.

    Checks:
        - Has the runtime changed?
        - Has the conservation law changed?
        - Has the task domain changed?
        - Are version-specific assumptions still true?
    """

    def validate(
        self, lesson: Lesson, environment: EnvironmentSnapshot
    ) -> Lesson:
        """Validate a single lesson against the environment.

        Returns the lesson with updated expiry_assessment.
        """
        # Deprecated lessons stay deprecated
        if lesson.lesson_type == LessonType.DEPRECATED:
            lesson.expiry_assessment = ExpiryAssessment.EXPIRED
            return lesson

        # Timeless lessons that aren't version-dependent stay active
        if lesson.lesson_type == LessonType.TIMELESS:
            # Still check conservation version for fence triggers
            if lesson.source == "fence_trigger":
                ctx = lesson.environment_context
                if self._conservation_changed(ctx, environment):
                    lesson.expiry_assessment = ExpiryAssessment.STALE
                    return lesson
            lesson.expiry_assessment = ExpiryAssessment.ACTIVE
            return lesson

        # Temporal lessons need full validation
        ctx = lesson.environment_context

        checks = [
            self._runtime_changed(ctx, environment),
            self._conservation_changed(ctx, environment),
            self._domain_changed(ctx, environment),
            self._api_version_changed(ctx, environment),
            self._rate_limit_changed(ctx, environment),
        ]

        changes = sum(checks)
        if changes == 0:
            lesson.expiry_assessment = ExpiryAssessment.ACTIVE
        elif changes <= 1:
            # One change — still potentially relevant but flag as stale
            lesson.expiry_assessment = ExpiryAssessment.STALE
            lesson.confidence *= 0.5  # reduce confidence in stale lessons
        else:
            # Multiple changes — the environment has shifted too much
            lesson.expiry_assessment = ExpiryAssessment.EXPIRED
            lesson.confidence *= 0.1

        return lesson

    def validate_batch(
        self,
        lessons: list[Lesson],
        environment: EnvironmentSnapshot,
    ) -> tuple[list[Lesson], list[Lesson], list[Lesson]]:
        """Validate a batch of lessons.

        Returns:
            A tuple of (active, stale, deprecated) lesson lists.
        """
        active: list[Lesson] = []
        stale: list[Lesson] = []
        deprecated: list[Lesson] = []

        for lesson in lessons:
            validated = self.validate(lesson, environment)
            if validated.expiry_assessment == ExpiryAssessment.ACTIVE:
                active.append(validated)
            elif validated.expiry_assessment == ExpiryAssessment.STALE:
                stale.append(validated)
            else:
                deprecated.append(validated)

        return active, stale, deprecated

    @staticmethod
    def _runtime_changed(
        ctx: dict[str, Any], env: EnvironmentSnapshot
    ) -> bool:
        """Check if runtime version has changed."""
        lesson_runtime = ctx.get("runtime", {}).get("version", "")
        if lesson_runtime and env.runtime_version:
            return lesson_runtime != env.runtime_version
        return False

    @staticmethod
    def _conservation_changed(
        ctx: dict[str, Any], env: EnvironmentSnapshot
    ) -> bool:
        """Check if conservation law version has changed."""
        lesson_conservation = ctx.get("conservation_version", "")
        if lesson_conservation and env.conservation_version:
            return lesson_conservation != env.conservation_version
        return False

    @staticmethod
    def _domain_changed(
        ctx: dict[str, Any], env: EnvironmentSnapshot
    ) -> bool:
        """Check if task domain has changed."""
        lesson_domain = ctx.get("task_domain", "")
        if lesson_domain and env.task_domain:
            return lesson_domain != env.task_domain
        return False

    @staticmethod
    def _api_version_changed(
        ctx: dict[str, Any], env: EnvironmentSnapshot
    ) -> bool:
        """Check if API versions referenced in the lesson have changed."""
        lesson_apis = ctx.get("api_versions", {})
        if not lesson_apis or not env.api_versions:
            return False
        for api, version in lesson_apis.items():
            if api in env.api_versions and env.api_versions[api] != version:
                return True
        return False

    @staticmethod
    def _rate_limit_changed(
        ctx: dict[str, Any], env: EnvironmentSnapshot
    ) -> bool:
        """Check if rate limits have changed."""
        lesson_limits = ctx.get("rate_limits", {})
        if not lesson_limits or not env.rate_limits:
            return False
        for service, limit in lesson_limits.items():
            if service in env.rate_limits and env.rate_limits[service] != limit:
                return True
        return False
