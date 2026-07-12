"""Distiller — extract lessons from a sunsetting model's record."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .lesson import Lesson, LessonType


class Distiller:
    """Extracts lessons from a sunset record.

    Sources:
        - Conversation logs / interaction history
        - Failure modes and corrections
        - Successful patterns
        - Conservation fence triggers (what got blocked and why)
    """

    def distill(self, sunset_record: dict[str, Any]) -> list[Lesson]:
        """Extract lessons from all sources in the sunset record.

        Args:
            sunset_record: A dict with optional keys:
                - conversation_logs: list of interaction dicts
                - failure_modes: list of failure dicts
                - successful_patterns: list of pattern dicts
                - fence_triggers: list of conservation fence triggers

        Returns:
            A list of Lessons sorted by confidence (descending).
        """
        lessons: list[Lesson] = []

        lessons.extend(self._from_conversation_logs(
            sunset_record.get("conversation_logs", [])
        ))
        lessons.extend(self._from_failure_modes(
            sunset_record.get("failure_modes", [])
        ))
        lessons.extend(self._from_successful_patterns(
            sunset_record.get("successful_patterns", [])
        ))
        lessons.extend(self._from_fence_triggers(
            sunset_record.get("fence_triggers", [])
        ))

        # Sort by confidence, descending
        lessons.sort(key=lambda l: l.confidence, reverse=True)
        return lessons

    def _from_conversation_logs(
        self, logs: list[dict[str, Any]]
    ) -> list[Lesson]:
        """Extract interaction-based lessons from conversation history."""
        lessons: list[Lesson] = []
        for entry in logs:
            if lesson := entry.get("lesson"):
                lessons.append(Lesson(
                    content=lesson,
                    confidence=entry.get("confidence", 0.5),
                    source="feedback",
                    environment_context=entry.get("context", {}),
                    lesson_type=self._infer_type(entry.get("context", {})),
                    learned_at=entry.get("timestamp", ""),
                    tags=entry.get("tags", ["conversation"]),
                ))
        return lessons

    def _from_failure_modes(
        self, failures: list[dict[str, Any]]
    ) -> list[Lesson]:
        """Extract lessons from recorded failures and their corrections."""
        lessons: list[Lesson] = []
        for failure in failures:
            correction = failure.get("correction", failure.get("description", ""))
            what_failed = failure.get("what", "unknown failure")
            content = f"Avoid: {what_failed}. Correction: {correction}"

            lessons.append(Lesson(
                content=content,
                confidence=self._failure_confidence(failure),
                source="failure",
                environment_context={
                    "failure_type": failure.get("type", "unknown"),
                    "severity": failure.get("severity", "medium"),
                    "runtime": failure.get("runtime", {}),
                },
                lesson_type=LessonType.TEMPORAL,  # failures are often environment-specific
                learned_at=failure.get("timestamp", ""),
                tags=failure.get("tags", ["failure"]),
            ))
        return lessons

    def _from_successful_patterns(
        self, patterns: list[dict[str, Any]]
    ) -> list[Lesson]:
        """Extract lessons from patterns that worked well."""
        lessons: list[Lesson] = []
        for pattern in patterns:
            content = pattern.get("lesson", pattern.get("description", ""))
            if not content:
                continue

            context = pattern.get("context", {})
            lessons.append(Lesson(
                content=content,
                confidence=pattern.get("confidence", 0.7),
                source="pattern",
                environment_context=context,
                lesson_type=self._infer_type(context),
                learned_at=pattern.get("timestamp", ""),
                tags=pattern.get("tags", ["pattern"]),
            ))
        return lessons

    def _from_fence_triggers(
        self, triggers: list[dict[str, Any]]
    ) -> list[Lesson]:
        """Extract lessons from conservation fence activations.

        Fence triggers represent hard boundaries that should never be crossed.
        These are typically timeless lessons.
        """
        lessons: list[Lesson] = []
        for trigger in triggers:
            rule = trigger.get("rule", "unknown conservation rule")
            reason = trigger.get("reason", "")
            content = f"Conservation fence: {rule}. {reason}".strip()

            lessons.append(Lesson(
                content=content,
                confidence=trigger.get("confidence", 0.95),  # fences are high-confidence
                source="fence_trigger",
                environment_context={
                    "rule": rule,
                    "triggered_by": trigger.get("triggered_by"),
                    "action_blocked": trigger.get("action_blocked"),
                },
                lesson_type=LessonType.TIMELESS,  # conservation laws are timeless
                learned_at=trigger.get("timestamp", ""),
                tags=trigger.get("tags", ["conservation", "fence"]),
            ))
        return lessons

    @staticmethod
    def _infer_type(context: dict[str, Any]) -> LessonType:
        """Heuristic: if context mentions specific versions/limits, it's temporal."""
        temporal_keys = {"api_version", "rate_limit", "model_version", "sdk_version"}
        if any(k in context for k in temporal_keys):
            return LessonType.TEMPORAL
        return LessonType.TIMELESS

    @staticmethod
    def _failure_confidence(failure: dict[str, Any]) -> float:
        """Higher confidence for failures with clear corrections."""
        base = 0.6
        if failure.get("correction"):
            base += 0.2
        if failure.get("severity") == "critical":
            base += 0.1
        return min(base, 1.0)
