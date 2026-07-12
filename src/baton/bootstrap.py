"""Bootstrap generator — produce the next generation's initial context."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ValidatedBrief


class BootstrapGenerator:
    """Generates the bootstrap brief for the next generation.

    Only active lessons are included. The brief is structured, not prose,
    so the offspring can parse and prioritize efficiently.
    """

    HEADER = "# Bootstrap Brief — Generational Handoff"
    FOOTER = (
        "\n---\n"
        "You are the next generation. These lessons are your inheritance, "
        "not your constraints. Validate them against your own experience. "
        "When in doubt, trust the present over the past."
    )

    def generate(self, validated: "ValidatedBrief") -> str:
        """Generate a structured bootstrap brief.

        Args:
            validated: A ValidatedBrief with active/stale/deprecated lessons.

        Returns:
            A structured bootstrap brief string.
        """
        brief = validated.handoff
        lines: list[str] = [
            self.HEADER,
            f"\nPassed from: {brief.model_id} (generation {brief.generation})",
            f"Compiled at: {brief.compiled_at}",
            f"Baton ID: {brief.id}",
        ]

        # Lineage pointer
        if brief.parent_brief_id:
            lines.append(f"Parent baton: {brief.parent_brief_id}")
        lines.append("")

        # Active lessons — grouped by type
        active_by_type = self._group_by_type(validated.active_lessons)
        if active_by_type:
            lines.append("## Active Lessons")
            for lesson_type, lessons in active_by_type.items():
                lines.append(f"\n### {lesson_type}")
                for lesson in lessons:
                    lines.append(self._format_lesson(lesson))

        # Stale lessons — included as cautionary context
        if validated.stale_lessons:
            lines.append("\n## Stale Lessons (verify before applying)")
            for lesson in validated.stale_lessons:
                lines.append(self._format_lesson(lesson, stale=True))

        # Deprecated — listed for audit, not included as guidance
        if validated.deprecated_lessons:
            lines.append("\n## Deprecated (do not apply)")
            for lesson in validated.deprecated_lessons:
                lines.append(f"- ~~{lesson.content}~~")

        # Stats
        total = len(brief.lessons)
        active = len(validated.active_lessons)
        lines.append(f"\n## Survival Rate")
        lines.append(f"{active}/{total} lessons survived validation")

        lines.append(self.FOOTER)
        return "\n".join(lines)

    @staticmethod
    def _group_by_type(lessons: list) -> dict[str, list]:
        """Group lessons by their lesson_type value."""
        groups: dict[str, list] = {}
        for lesson in lessons:
            key = lesson.lesson_type.value.title()
            groups.setdefault(key, []).append(lesson)
        return groups

    @staticmethod
    def _format_lesson(lesson, stale: bool = False) -> str:
        """Format a single lesson as a structured entry."""
        confidence_bar = "▓" * int(lesson.confidence * 5)
        confidence_bar += "░" * (5 - len(confidence_bar))
        prefix = "⚠️ " if stale else ""
        tags = f" [{', '.join(lesson.tags)}]" if lesson.tags else ""

        return (
            f"\n- {prefix}**{lesson.content}**{tags}\n"
            f"  - Confidence: {lesson.confidence:.0%} {confidence_bar}\n"
            f"  - Source: {lesson.source}"
        )
