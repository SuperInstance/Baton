"""Baton — Generational handoff for model lifecycle.

The relay between sunset and egg. Carries distilled wisdom from one
generation to the next, validating that lessons still apply.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .lesson import Lesson, LessonType, ExpiryAssessment
from .distiller import Distiller
from .validator import Validator, EnvironmentSnapshot
from .bootstrap import BootstrapGenerator
from .store import LineageStore

# Optional lineage-tracker bridge
try:
    from .lineage_bridge import LineageBridge
    HAS_LINEAGE_BRIDGE = True
except ImportError:
    LineageBridge = None  # type: ignore
    HAS_LINEAGE_BRIDGE = False

__version__ = "0.2.0"

__all__ = [
    "Baton",
    "AutoBaton",
    "HandoffBrief",
    "ValidatedBrief",
    "HandoffReport",
    "Lesson",
    "LessonType",
    "ExpiryAssessment",
    "EnvironmentSnapshot",
    "Validator",
    "Distiller",
    "BootstrapGenerator",
    "LineageStore",
    "LineageBridge",
    "HAS_LINEAGE_BRIDGE",
]


@dataclass
class HandoffBrief:
    """Distilled handoff from a sunsetting generation."""

    id: str
    model_id: str
    generation: int
    lessons: list[Lesson]
    compiled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    parent_brief_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "model_id": self.model_id,
            "generation": self.generation,
            "lessons": [l.to_dict() for l in self.lessons],
            "compiled_at": self.compiled_at,
            "parent_brief_id": self.parent_brief_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffBrief:
        return cls(
            id=data["id"],
            model_id=data["model_id"],
            generation=data["generation"],
            lessons=[Lesson.from_dict(l) for l in data["lessons"]],
            compiled_at=data.get("compiled_at", ""),
            parent_brief_id=data.get("parent_brief_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ValidatedBrief:
    """A handoff brief after environment validation."""

    handoff: HandoffBrief
    active_lessons: list[Lesson] = field(default_factory=list)
    stale_lessons: list[Lesson] = field(default_factory=list)
    deprecated_lessons: list[Lesson] = field(default_factory=list)
    validated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    environment: EnvironmentSnapshot | None = None

    @property
    def survival_rate(self) -> float:
        """Fraction of lessons that survived validation."""
        total = len(self.handoff.lessons)
        if total == 0:
            return 1.0
        return len(self.active_lessons) / total


class Baton:
    """The relay between sunset and egg.

    Compiles handoff briefs from sunsetting models, validates lessons
    against the current environment, and generates bootstrap context
    for the next generation.
    """

    def __init__(self, store_dir: str | Path = "./lineage"):
        self.store = LineageStore(store_dir)
        self.distiller = Distiller()
        self.validator = Validator()
        self.bootstrap_gen = BootstrapGenerator()

    def compile_handoff(
        self,
        sunset_record: dict[str, Any],
        parent_brief_id: str | None = None,
    ) -> HandoffBrief:
        """Distill a sunsetting model's experience into a handoff brief.

        Args:
            sunset_record: Record from the sunset process, containing
                conversation logs, failure modes, successful patterns,
                and conservation fence triggers.
            parent_brief_id: ID of the parent generation's brief, if any.

        Returns:
            A HandoffBrief with extracted lessons.
        """
        lessons = self.distiller.distill(sunset_record)
        generation = sunset_record.get("generation", 1)
        model_id = sunset_record.get("model_id", "unknown")

        brief = HandoffBrief(
            id=f"baton-{uuid4().hex[:12]}",
            model_id=model_id,
            generation=generation,
            lessons=lessons,
            parent_brief_id=parent_brief_id,
            metadata={
                "source_records": len(sunset_record.get("conversation_logs", [])),
                "failures_extracted": len(sunset_record.get("failure_modes", [])),
                "patterns_extracted": len(sunset_record.get("successful_patterns", [])),
            },
        )
        self.store.save(brief)
        return brief

    def validate_lessons(
        self,
        brief: HandoffBrief,
        current_environment: EnvironmentSnapshot,
    ) -> ValidatedBrief:
        """Check which lessons still apply. Flag stale ones.

        Args:
            brief: The handoff brief to validate.
            current_environment: Snapshot of the current runtime environment.

        Returns:
            A ValidatedBrief with lessons sorted into active/stale/deprecated.
        """
        active, stale, deprecated = self.validator.validate_batch(
            brief.lessons, current_environment
        )
        return ValidatedBrief(
            handoff=brief,
            active_lessons=active,
            stale_lessons=stale,
            deprecated_lessons=deprecated,
            environment=current_environment,
        )

    def generate_bootstrap(self, validated: ValidatedBrief) -> str:
        """Generate the system prompt / bootstrap context for the next generation.

        Args:
            validated: A validated brief with active/stale/deprecated lessons.

        Returns:
            A structured bootstrap brief string.
        """
        return self.bootstrap_gen.generate(validated)

    def trace_lineage(self, model_id: str) -> list[HandoffBrief]:
        """Trace the baton chain back through generations.

        Args:
            model_id: The model to trace lineage for.

        Returns:
            A list of HandoffBriefs from most recent to oldest.
        """
        return self.store.trace_lineage(model_id)


# Lazy import to avoid circular dependency at module load
def __getattr__(name: str):
    if name == "AutoBaton":
        from .auto import AutoBaton
        return AutoBaton
    if name == "HandoffReport":
        from .auto import HandoffReport
        return HandoffReport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
