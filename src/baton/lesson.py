"""Lesson data model for the baton system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class LessonType(str, Enum):
    """Classification of a lesson by temporal relevance."""

    TIMELESS = "timeless"      # Applies in any environment
    TEMPORAL = "temporal"      # Specific to parent's era
    DEPRECATED = "deprecated"  # No longer relevant


class ExpiryAssessment(str, Enum):
    """Whether a lesson has been assessed for expiry."""

    UNEVALUATED = "unevaluated"
    ACTIVE = "active"
    STALE = "stale"
    EXPIRED = "expired"


@dataclass
class Lesson:
    """A single lesson extracted from a model's experience.

    Attributes:
        content: The lesson text — what was learned.
        confidence: How strongly this lesson is held (0.0 to 1.0).
        source: How the lesson was learned.
        environment_context: What was true in the environment when learned.
        expiry_assessment: Whether this lesson still applies.
        lesson_type: Timeless, temporal, or deprecated.
        learned_at: When the lesson was first observed.
        tags: Free-form tags for categorization.
    """

    content: str
    confidence: float
    source: str  # experiment | feedback | failure | pattern | fence_trigger
    environment_context: dict[str, Any] = field(default_factory=dict)
    expiry_assessment: ExpiryAssessment = ExpiryAssessment.UNEVALUATED
    lesson_type: LessonType = LessonType.TEMPORAL
    learned_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if not self.content.strip():
            raise ValueError("lesson content must not be empty")

    @property
    def is_actionable(self) -> bool:
        """Whether this lesson should influence the next generation."""
        return (
            self.expiry_assessment == ExpiryAssessment.ACTIVE
            and self.lesson_type != LessonType.DEPRECATED
            and self.confidence >= 0.3
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "confidence": self.confidence,
            "source": self.source,
            "environment_context": self.environment_context,
            "expiry_assessment": self.expiry_assessment.value,
            "lesson_type": self.lesson_type.value,
            "learned_at": self.learned_at,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lesson:
        return cls(
            content=data["content"],
            confidence=data["confidence"],
            source=data["source"],
            environment_context=data.get("environment_context", {}),
            expiry_assessment=ExpiryAssessment(data.get("expiry_assessment", "unevaluated")),
            lesson_type=LessonType(data.get("lesson_type", "temporal")),
            learned_at=data.get("learned_at", ""),
            tags=data.get("tags", []),
        )
