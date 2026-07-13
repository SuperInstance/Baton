"""Bridge between baton lessons and lineage-tracker bloodline records.

When a lesson is recorded via baton, this bridge optionally logs the
event to lineage-tracker for fine-tune bloodline tracking. This creates
a provenance chain: each lesson carries its ancestry forward.

Usage:
    from baton.lineage_bridge import LineageBridge

    bridge = LineageBridge(lineage_tracker)
    bridge.record_lesson(model_id, lesson, brief_id)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .lesson import Lesson, LessonType, ExpiryAssessment


class LineageBridge:
    """Bridge baton lessons into lineage-tracker breeding records.

    Each lesson recorded in a baton handoff can be logged as a metadata
    entry in lineage-tracker, creating a searchable trail of what wisdom
    was passed forward and from whom.
    """

    def __init__(self, tracker):
        """Initialize the bridge.

        Args:
            tracker: A lineage_tracker.LineageTracker instance.
        """
        self.tracker = tracker

    def record_lesson(
        self,
        model_id: str,
        lesson: Lesson,
        brief_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Log a baton lesson as a lineage-tracker metadata entry.

        Args:
            model_id: The model that produced or received this lesson.
            lesson: The baton Lesson object.
            brief_id: The handoff brief this lesson belongs to.

        Returns:
            A dict with the lineage entry data.
        """
        entry = {
            "type": "baton_lesson",
            "model_id": model_id,
            "lesson_content": lesson.content,
            "lesson_confidence": lesson.confidence,
            "lesson_source": lesson.source,
            "lesson_type": lesson.lesson_type.value,
            "expiry": lesson.expiry_assessment.value,
            "is_actionable": lesson.is_actionable,
            "brief_id": brief_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tags": lesson.tags,
        }

        # If the model exists in lineage-tracker, attach as trait metadata
        try:
            model = self.tracker.store.get_model(model_id)
        except Exception:
            model = None
        if model is not None:
            traits = dict(model.traits)
            lessons_log = traits.get("baton_lessons", [])
            lessons_log.append({
                "content": lesson.content,
                "confidence": lesson.confidence,
                "source": lesson.source,
                "brief_id": brief_id,
            })
            traits["baton_lessons"] = lessons_log
            traits["last_lesson_at"] = entry["timestamp"]
            traits["total_lessons"] = len(lessons_log)

            # Update the model with new traits
            from lineage_tracker.model import Model
            updated = Model(
                name=model.name,
                version=model.version,
                traits=traits,
                checksum=model.checksum,
            )
            self.tracker.store.save_model(updated)

        return entry

    def record_handoff(
        self,
        parent_model: str,
        child_model: str,
        brief_id: str,
        lesson_count: int,
        active_count: int = 0,
        method: str = "baton_handoff",
    ) -> Any:
        """Record a full baton handoff as a breeding event in lineage-tracker.

        This creates the formal bloodline link between parent and child
        models through the baton relay.

        Args:
            parent_model: The sunsetting model's name.
            child_model: The next-generation model's name.
            brief_id: The handoff brief ID.
            lesson_count: Total lessons in the brief.
            active_count: How many survived validation.
            method: Breeding method label.

        Returns:
            The created child Model from lineage-tracker.
        """
        metadata = {
            "brief_id": brief_id,
            "lessons_passed": active_count,
            "lessons_total": lesson_count,
            "survival_rate": active_count / lesson_count if lesson_count > 0 else 0.0,
            "bridge": "baton_lineage",
        }

        return self.tracker.record_breeding(
            parents=[parent_model],
            child_name=child_model,
            method=method,
            metadata=metadata,
            child_traits={
                "handoff_brief": brief_id,
                "inherited_lessons": active_count,
            },
        )

    def get_lesson_lineage(self, model_id: str) -> list[dict[str, Any]]:
        """Retrieve all baton lessons recorded for a model.

        Walks the lineage chain and collects all lessons from
        the model and its ancestors.

        Returns:
            List of lesson entries with model attribution.
        """
        lineage = self.tracker.get_lineage(model_id)
        all_lessons: list[dict[str, Any]] = []

        for gen in lineage:
            model = gen.model
            lessons = model.traits.get("baton_lessons", [])
            for lesson in lessons:
                all_lessons.append({
                    **lesson,
                    "from_model": model.name,
                    "generation": gen.generation,
                })

        return all_lessons


__all__ = ["LineageBridge"]
