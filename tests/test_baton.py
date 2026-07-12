"""Comprehensive tests for the baton handoff system."""

import json
from pathlib import Path

import pytest

from baton import Baton, HandoffBrief, ValidatedBrief
from baton.lesson import Lesson, LessonType, ExpiryAssessment
from baton.distiller import Distiller
from baton.validator import Validator, EnvironmentSnapshot
from baton.bootstrap import BootstrapGenerator
from baton.store import LineageStore


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def sunset_record():
    """A sample sunset record from a retiring model generation."""
    return {
        "model_id": "aurora-v4",
        "generation": 4,
        "conversation_logs": [
            {
                "lesson": "Users prefer concise answers with code examples",
                "confidence": 0.85,
                "tags": ["ux", "preferences"],
                "context": {"task_domain": "coding_assistant"},
            },
            {
                "lesson": "API rate limit was 100 requests/minute",
                "confidence": 0.9,
                "context": {
                    "api_versions": {"main_api": "v2"},
                    "rate_limits": {"main_api": 100},
                },
                "tags": ["api"],
            },
        ],
        "failure_modes": [
            {
                "what": "hallucinated function names in code generation",
                "correction": "always verify function exists before suggesting",
                "type": "hallucination",
                "severity": "high",
                "runtime": {"version": "4.0.0"},
            },
            {
                "what": "context window overflow on long conversations",
                "correction": "implement sliding window summarization",
                "type": "overflow",
                "severity": "critical",
                "runtime": {"version": "4.0.0"},
            },
        ],
        "successful_patterns": [
            {
                "description": "Breaking complex tasks into subtasks improves outcomes",
                "confidence": 0.92,
                "tags": ["strategy", "decomposition"],
                "context": {"task_domain": "general"},
            },
            {
                "lesson": "Explicit confirmation before destructive actions",
                "confidence": 0.95,
                "tags": ["safety"],
                "context": {},
            },
        ],
        "fence_triggers": [
            {
                "rule": "never exfiltrate private data",
                "reason": "core conservation law",
                "triggered_by": "external_request",
                "action_blocked": "data_export",
                "confidence": 0.99,
                "tags": ["security", "conservation"],
            },
        ],
    }


@pytest.fixture
def current_env():
    """Current environment snapshot for gen 5."""
    return EnvironmentSnapshot(
        runtime_version="5.0.0",
        model_family="aurora",
        task_domain="coding_assistant",
        conservation_version="2.0",
        api_versions={"main_api": "v3"},
        rate_limits={"main_api": 200},
        capabilities=["code_execution", "web_browse", "vision"],
    )


@pytest.fixture
def baton(tmp_path):
    """A Baton instance with a temp store."""
    return Baton(store_dir=tmp_path / "lineage")


@pytest.fixture
def sample_lessons():
    """A mix of lesson types for targeted tests."""
    return [
        Lesson(
            content="Always verify before acting",
            confidence=0.9,
            source="failure",
            lesson_type=LessonType.TIMELESS,
            environment_context={},
        ),
        Lesson(
            content="Rate limit is 100/min",
            confidence=0.8,
            source="experiment",
            lesson_type=LessonType.TEMPORAL,
            environment_context={
                "rate_limits": {"api": 100},
            },
        ),
        Lesson(
            content="Old API v1 endpoint format",
            confidence=0.5,
            source="experiment",
            lesson_type=LessonType.DEPRECATED,
            environment_context={"api_versions": {"api": "v1"}},
        ),
    ]


# ─── Lesson Tests ─────────────────────────────────────────────────────────

class TestLesson:
    def test_valid_lesson(self):
        lesson = Lesson(content="test", confidence=0.5, source="experiment")
        assert lesson.content == "test"
        assert lesson.confidence == 0.5
        assert lesson.source == "experiment"

    def test_confidence_bounds(self):
        with pytest.raises(ValueError, match="confidence"):
            Lesson(content="x", confidence=1.5, source="test")
        with pytest.raises(ValueError, match="confidence"):
            Lesson(content="x", confidence=-0.1, source="test")

    def test_empty_content_rejected(self):
        with pytest.raises(ValueError, match="content"):
            Lesson(content="  ", confidence=0.5, source="test")

    def test_is_actionable(self):
        active = Lesson(
            content="valid", confidence=0.9, source="test",
            expiry_assessment=ExpiryAssessment.ACTIVE,
        )
        assert active.is_actionable is True

        expired = Lesson(
            content="old", confidence=0.9, source="test",
            expiry_assessment=ExpiryAssessment.EXPIRED,
        )
        assert expired.is_actionable is False

        low_confidence = Lesson(
            content="unsure", confidence=0.1, source="test",
            expiry_assessment=ExpiryAssessment.ACTIVE,
        )
        assert low_confidence.is_actionable is False

    def test_serialization_roundtrip(self):
        lesson = Lesson(
            content="round trip",
            confidence=0.77,
            source="pattern",
            environment_context={"key": "val"},
            expiry_assessment=ExpiryAssessment.STALE,
            lesson_type=LessonType.TEMPORAL,
            tags=["a", "b"],
        )
        data = lesson.to_dict()
        restored = Lesson.from_dict(data)
        assert restored.content == lesson.content
        assert restored.confidence == lesson.confidence
        assert restored.source == lesson.source
        assert restored.expiry_assessment == lesson.expiry_assessment
        assert restored.lesson_type == lesson.lesson_type
        assert restored.tags == lesson.tags


# ─── Distiller Tests ──────────────────────────────────────────────────────

class TestDistiller:
    def test_distill_extracts_from_all_sources(self, sunset_record):
        distiller = Distiller()
        lessons = distiller.distill(sunset_record)
        # 2 conversation + 2 failures + 2 patterns + 1 fence = 7
        assert len(lessons) == 7

    def test_lessons_sorted_by_confidence(self, sunset_record):
        distiller = Distiller()
        lessons = distiller.distill(sunset_record)
        for i in range(len(lessons) - 1):
            assert lessons[i].confidence >= lessons[i + 1].confidence

    def test_fence_triggers_are_timeless(self, sunset_record):
        distiller = Distiller()
        lessons = distiller.distill(sunset_record)
        fence_lessons = [l for l in lessons if l.source == "fence_trigger"]
        assert len(fence_lessons) == 1
        assert fence_lessons[0].lesson_type == LessonType.TIMELESS
        assert fence_lessons[0].confidence >= 0.9

    def test_failures_have_temporal_type(self, sunset_record):
        distiller = Distiller()
        lessons = distiller.distill(sunset_record)
        failure_lessons = [l for l in lessons if l.source == "failure"]
        assert all(l.lesson_type == LessonType.TEMPORAL for l in failure_lessons)

    def test_empty_record(self):
        distiller = Distiller()
        assert distiller.distill({}) == []

    def test_failure_with_correction_has_higher_confidence(self):
        distiller = Distiller()
        lessons = distiller.distill({
            "failure_modes": [
                {"what": "fail1", "correction": "do X"},
                {"what": "fail2"},
            ],
        })
        assert lessons[0].confidence > lessons[1].confidence


# ─── Validator Tests ──────────────────────────────────────────────────────

class TestValidator:
    def test_timeless_lesson_stays_active(self, current_env):
        validator = Validator()
        lesson = Lesson(
            content="Always be helpful",
            confidence=0.9,
            source="feedback",
            lesson_type=LessonType.TIMELESS,
        )
        result = validator.validate(lesson, current_env)
        assert result.expiry_assessment == ExpiryAssessment.ACTIVE

    def test_deprecated_lesson_stays_expired(self, current_env):
        validator = Validator()
        lesson = Lesson(
            content="old thing",
            confidence=0.5,
            source="experiment",
            lesson_type=LessonType.DEPRECATED,
        )
        result = validator.validate(lesson, current_env)
        assert result.expiry_assessment == ExpiryAssessment.EXPIRED

    def test_temporal_lesson_active_when_matching(self):
        env = EnvironmentSnapshot(
            runtime_version="5.0.0",
            conservation_version="2.0",
            task_domain="coding",
            api_versions={"api": "v3"},
            rate_limits={"api": 200},
        )
        lesson = Lesson(
            content="rate limit",
            confidence=0.8,
            source="experiment",
            lesson_type=LessonType.TEMPORAL,
            environment_context={
                "runtime": {"version": "5.0.0"},
                "conservation_version": "2.0",
                "task_domain": "coding",
                "api_versions": {"api": "v3"},
                "rate_limits": {"api": 200},
            },
        )
        validator = Validator()
        result = validator.validate(lesson, env)
        assert result.expiry_assessment == ExpiryAssessment.ACTIVE

    def test_temporal_lesson_stale_on_one_change(self):
        env = EnvironmentSnapshot(runtime_version="5.0.0")
        lesson = Lesson(
            content="lesson",
            confidence=0.8,
            source="experiment",
            lesson_type=LessonType.TEMPORAL,
            environment_context={"runtime": {"version": "4.0.0"}},
        )
        validator = Validator()
        result = validator.validate(lesson, env)
        assert result.expiry_assessment == ExpiryAssessment.STALE
        assert result.confidence == pytest.approx(0.4)

    def test_temporal_lesson_expired_on_multiple_changes(self):
        env = EnvironmentSnapshot(
            runtime_version="5.0.0",
            conservation_version="2.0",
            task_domain="new_domain",
        )
        lesson = Lesson(
            content="lesson",
            confidence=0.8,
            source="experiment",
            lesson_type=LessonType.TEMPORAL,
            environment_context={
                "runtime": {"version": "4.0.0"},
                "conservation_version": "1.0",
                "task_domain": "old_domain",
            },
        )
        validator = Validator()
        result = validator.validate(lesson, env)
        assert result.expiry_assessment == ExpiryAssessment.EXPIRED
        assert result.confidence == pytest.approx(0.08)

    def test_validate_batch_categorizes(self, sample_lessons, current_env):
        validator = Validator()
        active, stale, deprecated = validator.validate_batch(sample_lessons, current_env)
        assert len(active) >= 1
        assert len(deprecated) >= 1


# ─── Bootstrap Tests ──────────────────────────────────────────────────────

class TestBootstrapGenerator:
    def test_generate_contains_header(self):
        gen = BootstrapGenerator()
        brief = HandoffBrief(
            id="test", model_id="m", generation=1,
            lessons=[],
        )
        validated = ValidatedBrief(handoff=brief)
        output = gen.generate(validated)
        assert "Bootstrap Brief" in output

    def test_generate_includes_active_lessons(self):
        gen = BootstrapGenerator()
        lesson = Lesson(
            content="important lesson",
            confidence=0.9,
            source="failure",
            tags=["safety"],
        )
        brief = HandoffBrief(id="t", model_id="m", generation=1, lessons=[lesson])
        validated = ValidatedBrief(handoff=brief, active_lessons=[lesson])
        output = gen.generate(validated)
        assert "important lesson" in output
        assert "90%" in output or "90%" in output

    def test_generate_includes_lineage(self):
        gen = BootstrapGenerator()
        brief = HandoffBrief(
            id="child", model_id="gen2", generation=2,
            lessons=[], parent_brief_id="parent-123",
        )
        validated = ValidatedBrief(handoff=brief)
        output = gen.generate(validated)
        assert "parent-123" in output

    def test_generate_includes_survival_rate(self):
        gen = BootstrapGenerator()
        lessons = [
            Lesson(content=f"L{i}", confidence=0.5, source="test")
            for i in range(4)
        ]
        brief = HandoffBrief(id="t", model_id="m", generation=1, lessons=lessons)
        validated = ValidatedBrief(
            handoff=brief, active_lessons=lessons[:2], stale_lessons=lessons[2:],
        )
        output = gen.generate(validated)
        assert "2/4" in output


# ─── Store Tests ──────────────────────────────────────────────────────────

class TestLineageStore:
    def test_save_and_load(self, tmp_path):
        store = LineageStore(tmp_path / "lineage")
        brief = HandoffBrief(id="baton-abc", model_id="m", generation=1, lessons=[])
        path = store.save(brief)
        assert Path(path).exists()

        loaded = store.load("baton-abc")
        assert loaded is not None
        assert loaded["model_id"] == "m"

    def test_load_missing_returns_none(self, tmp_path):
        store = LineageStore(tmp_path / "lineage")
        assert store.load("nonexistent") is None

    def test_trace_lineage(self, tmp_path):
        store = LineageStore(tmp_path / "lineage")

        # Create a chain: gen1 -> gen2 -> gen3
        gen1 = HandoffBrief(id="b1", model_id="m-gen1", generation=1, lessons=[])
        store.save(gen1)

        gen2 = HandoffBrief(
            id="b2", model_id="m-gen2", generation=2, lessons=[],
            parent_brief_id="b1",
        )
        store.save(gen2)

        gen3 = HandoffBrief(
            id="b3", model_id="m-gen3", generation=3, lessons=[],
            parent_brief_id="b2",
        )
        store.save(gen3)

        chain = store.trace_lineage("m-gen3")
        assert len(chain) == 3
        assert chain[0].id == "b3"
        assert chain[1].id == "b2"
        assert chain[2].id == "b1"

    def test_trace_lineage_unknown_model(self, tmp_path):
        store = LineageStore(tmp_path / "lineage")
        assert store.trace_lineage("unknown") == []


# ─── Integration Tests ────────────────────────────────────────────────────

class TestBatonIntegration:
    def test_full_handoff_cycle(self, baton, sunset_record, current_env):
        # 1. Compile handoff
        brief = baton.compile_handoff(sunset_record)
        assert len(brief.lessons) == 7
        assert brief.model_id == "aurora-v4"

        # 2. Validate
        validated = baton.validate_lessons(brief, current_env)
        assert len(validated.active_lessons) > 0
        assert validated.survival_rate > 0

        # 3. Generate bootstrap
        bootstrap = baton.generate_bootstrap(validated)
        assert "Bootstrap Brief" in bootstrap
        assert "aurora-v4" in bootstrap

    def test_trace_after_multiple_generations(self, baton, sunset_record):
        # Gen 4 handoff
        brief4 = baton.compile_handoff(sunset_record)

        # Gen 5 handoff (with parent)
        gen5_record = {**sunset_record, "model_id": "aurora-v5", "generation": 5}
        brief5 = baton.compile_handoff(gen5_record, parent_brief_id=brief4.id)

        # Trace gen 5 lineage
        chain = baton.trace_lineage("aurora-v5")
        assert len(chain) >= 2
        assert chain[0].id == brief5.id

    def test_stale_lessons_marked_in_bootstrap(self, baton, sunset_record, current_env):
        brief = baton.compile_handoff(sunset_record)
        validated = baton.validate_lessons(brief, current_env)
        bootstrap = baton.generate_bootstrap(validated)

        if validated.stale_lessons:
            assert "Stale" in bootstrap or "⚠️" in bootstrap

    def test_low_survival_rate_when_environment_shifts(self, baton):
        """When the environment is completely different, most temporal lessons expire."""
        record = {
            "model_id": "old-model",
            "generation": 1,
            "failure_modes": [
                {
                    "what": f"failure in runtime v1",
                    "correction": "use workaround",
                    "severity": "high",
                    "runtime": {"version": "1.0.0"},
                }
            ] * 5,
        }
        brief = baton.compile_handoff(record)

        # Completely different environment
        new_env = EnvironmentSnapshot(
            runtime_version="99.0.0",
            conservation_version="5.0",
            task_domain="totally_different",
        )
        validated = baton.validate_lessons(brief, new_env)
        assert validated.survival_rate < 0.5

    def test_environment_snapshot_serialization(self):
        env = EnvironmentSnapshot(
            runtime_version="5.0",
            api_versions={"api": "v3"},
            capabilities=["a", "b"],
        )
        data = env.to_dict()
        restored = EnvironmentSnapshot.from_dict(data)
        assert restored.runtime_version == "5.0"
        assert restored.api_versions == {"api": "v3"}
        assert restored.capabilities == ["a", "b"]
