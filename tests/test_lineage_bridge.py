"""Tests for baton ↔ lineage-tracker bridge."""

import pytest
import tempfile
import os
from baton.lesson import Lesson, LessonType, ExpiryAssessment
from baton.lineage_bridge import LineageBridge
from lineage_tracker import LineageTracker


@pytest.fixture
def tracker():
    """Create a lineage tracker with a temp file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as f:
        import json
        json.dump({"models": {}, "breeding_records": [], "generations": {}}, f)
        path = f.name
    try:
        yield LineageTracker(path=path)
    finally:
        os.unlink(path)


@pytest.fixture
def bridge(tracker):
    """Create a lineage bridge."""
    return LineageBridge(tracker)


@pytest.fixture
def registered_model(tracker):
    """Register a parent model in the tracker."""
    tracker.record_breeding(
        parents=["root"],
        child_name="test-model",
        method="full",
        child_traits={"baseline_score": 0.75},
    )
    return "test-model"


class TestRecordLesson:
    def test_record_lesson_returns_entry(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        lesson = Lesson(
            content="Always validate before distilling",
            confidence=0.9,
            source="failure",
        )
        entry = bridge.record_lesson("test-model", lesson, brief_id="baton-001")
        assert entry["type"] == "baton_lesson"
        assert entry["model_id"] == "test-model"
        assert entry["lesson_content"] == "Always validate before distilling"
        assert entry["brief_id"] == "baton-001"

    def test_record_lesson_attaches_to_model(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        lesson = Lesson(
            content="Temperature matters more than salinity",
            confidence=0.85,
            source="pattern",
            tags=["ecology", "ocean"],
        )
        bridge.record_lesson("test-model", lesson)

        model = tracker.store.get_model("test-model")
        assert model is not None
        assert "baton_lessons" in model.traits
        assert len(model.traits["baton_lessons"]) == 1
        assert model.traits["baton_lessons"][0]["content"] == "Temperature matters more than salinity"
        assert model.traits["total_lessons"] == 1

    def test_record_multiple_lessons(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        for i in range(3):
            lesson = Lesson(
                content=f"Lesson number {i}",
                confidence=0.5 + i * 0.1,
                source="experiment",
            )
            bridge.record_lesson("test-model", lesson)

        model = tracker.store.get_model("test-model")
        assert model.traits["total_lessons"] == 3
        assert len(model.traits["baton_lessons"]) == 3

    def test_record_lesson_for_unknown_model(self, bridge, tracker):
        """Should not fail if model doesn't exist in tracker yet."""
        lesson = Lesson(
            content="Test lesson for unknown model",
            confidence=0.7,
            source="feedback",
        )
        entry = bridge.record_lesson("nonexistent-model", lesson)
        assert entry["model_id"] == "nonexistent-model"
        assert entry["lesson_content"] == "Test lesson for unknown model"


class TestRecordHandoff:
    def test_record_handoff_creates_breeding_record(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        child = bridge.record_handoff(
            parent_model="test-model",
            child_model="test-model-v2",
            brief_id="baton-002",
            lesson_count=10,
            active_count=8,
        )
        assert child.name == "test-model-v2"
        assert child.traits.get("inherited_lessons") == 8

        # Verify breeding record
        records = tracker.list_breeding_records()
        handoff_records = [r for r in records if r.method == "baton_handoff"]
        assert len(handoff_records) == 1
        assert handoff_records[0].metadata["brief_id"] == "baton-002"
        assert handoff_records[0].metadata["survival_rate"] == pytest.approx(0.8)

    def test_record_handoff_with_zero_lessons(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        child = bridge.record_handoff(
            parent_model="test-model",
            child_model="empty-child",
            brief_id="baton-empty",
            lesson_count=0,
            active_count=0,
        )
        assert child is not None
        records = tracker.list_breeding_records()
        handoff = [r for r in records if r.metadata.get("brief_id") == "baton-empty"]
        assert handoff[0].metadata["survival_rate"] == 0.0


class TestGetLessonLineage:
    def test_get_lesson_lineage_empty(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        lessons = bridge.get_lesson_lineage("test-model")
        # No lessons recorded yet
        assert isinstance(lessons, list)

    def test_get_lesson_lineage_with_lessons(self, bridge, tracker, registered_model):
        tracker.store._cache = None
        lesson = Lesson(
            content="Deep insight about the ocean",
            confidence=0.92,
            source="pattern",
        )
        bridge.record_lesson("test-model", lesson, brief_id="baton-lin-1")
        tracker.store._cache = None

        # Record handoff to child
        bridge.record_handoff("test-model", "child-model", "baton-lin-2", 5, 3)

        # Add a lesson to the child too
        lesson2 = Lesson(
            content="Child generation insight",
            confidence=0.88,
            source="experiment",
        )
        bridge.record_lesson("child-model", lesson2, brief_id="baton-lin-3")
        tracker.store._cache = None

        lineage = bridge.get_lesson_lineage("child-model")
        assert len(lineage) >= 1
        contents = [l.get("content") for l in lineage]
        assert "Child generation insight" in contents
