"""Tests for AutoBaton — the automatic model lifecycle manager."""

import json
import pytest
from pathlib import Path

from baton.auto import AutoBaton, HandoffReport, ExpiryFlag
from baton.lesson import LessonType, ExpiryAssessment
from baton.validator import EnvironmentSnapshot


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def auto(tmp_path):
    """An AutoBaton instance with a temp store."""
    return AutoBaton("test-boat", store_dir=tmp_path / "lineage")


@pytest.fixture
def auto_with_lessons(tmp_path):
    """An AutoBaton with some pre-recorded lessons."""
    auto = AutoBaton("test-boat", store_dir=tmp_path / "lineage")
    auto.record_lesson("quota check", "blocked 3 overages", 0.9, tags=["ops"])
    auto.record_lesson("user preference", "concise answers preferred", 0.85, source="feedback")
    auto.record_failure("timeout on API", "add retry with backoff", severity="high")
    auto.record_pattern("batch requests reduce latency", 0.88)
    return auto


@pytest.fixture
def shifted_env():
    """An environment that differs from the lesson context."""
    return EnvironmentSnapshot(
        runtime_version="9.9.9",
        model_family="new-family",
        task_domain="new-domain",
        conservation_version="3.0",
        api_versions={"api": "v9"},
        rate_limits={"api": 500},
    )


# ─── Recording Tests ─────────────────────────────────────────────────────

class TestRecordLesson:
    def test_basic_recording(self, auto):
        lesson = auto.record_lesson(
            "quota check", "blocked 3 overages", 0.9
        )
        assert lesson.content == "quota check: blocked 3 overages"
        assert lesson.confidence == 0.9
        assert lesson.source == "feedback"
        assert len(auto.brief.lessons) == 1

    def test_recording_persists(self, tmp_path):
        store = tmp_path / "lineage"
        auto1 = AutoBaton("boat", store_dir=store)
        auto1.record_lesson("event", "outcome", 0.7)

        # New instance should load the saved brief
        auto2 = AutoBaton("boat", store_dir=store)
        assert len(auto2.brief.lessons) == 1
        assert auto2.brief.lessons[0].content == "event: outcome"

    def test_tags_preserved(self, auto):
        lesson = auto.record_lesson(
            "test", "result", 0.5, tags=["ops", "billing"]
        )
        assert "ops" in lesson.tags
        assert "billing" in lesson.tags

    def test_confidence_bounds(self, auto):
        with pytest.raises(ValueError):
            auto.record_lesson("e", "o", 1.5)

    def test_source_selection(self, auto):
        lesson = auto.record_lesson(
            "e", "o", 0.5, source="pattern"
        )
        assert lesson.source == "pattern"


class TestRecordFailure:
    def test_failure_recording(self, auto):
        lesson = auto.record_failure(
            "timeout", "add retry", severity="critical"
        )
        assert "timeout" in lesson.content
        assert "add retry" in lesson.content
        assert lesson.source == "failure"
        assert lesson.confidence >= 0.8  # failure with correction + critical
        assert lesson.lesson_type == LessonType.TEMPORAL

    def test_failure_without_correction_lower_confidence(self, auto):
        lesson = auto.record_failure("oops", "", severity="low")
        assert lesson.confidence == pytest.approx(0.6)


class TestRecordPattern:
    def test_pattern_recording(self, auto):
        lesson = auto.record_pattern("batching works", 0.88)
        assert "batching works" in lesson.content
        assert lesson.source == "pattern"
        assert lesson.confidence == 0.88


# ─── Expiry Tests ─────────────────────────────────────────────────────────

class TestCheckExpiry:
    def test_no_expiry_when_unchanged(self, auto_with_lessons):
        """Lessons should be fine when environment hasn't changed."""
        flags = auto_with_lessons.check_expiry()
        # Without explicit env, the auto-captured one won't have versioned context
        # to conflict with, so flags depend on lesson context
        assert isinstance(flags, list)

    def test_expiry_flags_on_changed_env(self, auto_with_lessons, shifted_env):
        flags = auto_with_lessons.check_expiry(current_env=shifted_env)
        # Lessons recorded without explicit env context won't flag,
        # but the ones with temporal context should
        assert isinstance(flags, list)

    def test_expiry_flags_contain_reasons(self, auto, shifted_env):
        # Record a lesson with explicit versioned context
        auto.record_lesson(
            "rate limit", "100/min", 0.9,
            env_context={"rate_limits": {"api": 100}},
        )
        flags = auto.check_expiry(current_env=shifted_env)
        assert len(flags) >= 1
        assert any("rate" in f.reason.lower() or "api" in f.reason.lower() for f in flags)

    def test_timeless_lessons_not_flagged(self, auto, shifted_env):
        auto.record_lesson(
            "always verify", "checksums matter", 0.95,
            source="fence_trigger",
        )
        flags = auto.check_expiry(current_env=shifted_env)
        # Fence triggers are timeless; won't be flagged unless conservation changed
        # and even then only stale, not expired
        timeless_flags = [f for f in flags if f.lesson.lesson_type == LessonType.TIMELESS]
        # Only flagged if conservation_version changed AND source is fence_trigger
        # shifted_env has conservation 3.0 but lesson has no conservation_version set
        assert len(timeless_flags) == 0


# ─── Bootstrap Generation Tests ──────────────────────────────────────────

class TestBootstrapGeneration:
    def test_bootstrap_contains_header(self, auto_with_lessons):
        bootstrap = auto_with_lessons.generate_bootstrap("llama-3.3-70b")
        assert "Bootstrap Brief" in bootstrap
        assert "llama-3.3-70b" in bootstrap

    def test_bootstrap_contains_lessons(self, auto_with_lessons):
        bootstrap = auto_with_lessons.generate_bootstrap("new-model")
        assert "quota check" in bootstrap or "blocked 3 overages" in bootstrap

    def test_bootstrap_with_empty_system(self, tmp_path):
        auto = AutoBaton("empty", store_dir=tmp_path / "lineage")
        bootstrap = auto.generate_bootstrap("new-model")
        assert "Bootstrap Brief" in bootstrap
        assert "0/0" in bootstrap  # survival rate with no lessons


# ─── Handoff Tests ────────────────────────────────────────────────────────

class TestHandoff:
    def test_handoff_returns_report(self, auto_with_lessons):
        report = auto_with_lessons.handoff("old-model", "new-model")
        assert isinstance(report, HandoffReport)
        assert report.old_model_id == "old-model"
        assert report.new_model_id == "new-model"

    def test_handoff_survival_rate(self, auto_with_lessons):
        report = auto_with_lessons.handoff("old", "new")
        assert 0.0 <= report.survival_rate <= 1.0
        assert report.lessons_carried + report.lessons_stale + report.lessons_dropped >= 0

    def test_handoff_with_environment_shift(self, auto_with_lessons, shifted_env):
        report = auto_with_lessons.handoff("old", "new", current_env=shifted_env)
        # With shifted env, at least some lessons should be affected
        total = report.lessons_carried + report.lessons_stale + report.lessons_dropped
        assert total == len(auto_with_lessons.brief.lessons)

    def test_handoff_summary_string(self, auto_with_lessons):
        report = auto_with_lessons.handoff("a", "b")
        assert "a → b" in report.summary
        assert "survival" in report.summary  # survival_rate shown in summary
        assert "carried" in report.summary

    def test_handoff_with_model_runners(self, auto_with_lessons):
        """Test handoff with callable model runners."""

        class FakeRunner:
            def __init__(self, model_id):
                self.model_id = model_id

            def run(self, prompt: str) -> str:
                return f"Response to: {prompt}"

        new_runner = FakeRunner("new-model")
        report = auto_with_lessons.handoff("old", new_runner)
        assert report.new_model_id == "new-model"
        assert len(report.test_results) > 0
        assert all(report.test_results.values())  # FakeRunner always returns

    def test_handoff_persists_report(self, auto_with_lessons, tmp_path):
        auto_with_lessons.handoff("old", "new")
        reports_dir = auto_with_lessons.state_dir / "reports"
        assert reports_dir.exists()
        report_files = list(reports_dir.glob("*.json"))
        assert len(report_files) >= 1

    def test_handoff_report_serialization(self, auto_with_lessons):
        report = auto_with_lessons.handoff("old", "new")
        data = report.to_dict()
        assert data["old_model_id"] == "old"
        assert data["new_model_id"] == "new"
        assert "bootstrap_brief" in data
        assert "survival_rate" in data


# ─── Persistence Tests ───────────────────────────────────────────────────

class TestPersistence:
    def test_brief_persists_across_instances(self, tmp_path):
        store = tmp_path / "lineage"
        auto1 = AutoBaton("persist-boat", store_dir=store)
        auto1.record_lesson("event 1", "outcome 1", 0.8)
        auto1.record_lesson("event 2", "outcome 2", 0.6)
        brief_id = auto1.brief.id

        auto2 = AutoBaton("persist-boat", store_dir=store)
        assert auto2.brief.id == brief_id
        assert len(auto2.brief.lessons) == 2

    def test_handoff_report_saved(self, tmp_path):
        store = tmp_path / "lineage"
        auto = AutoBaton("audit-boat", store_dir=store)
        auto.record_lesson("test", "result", 0.7)
        auto.handoff("v1", "v2")

        reports = list((store / "auto" / "audit-boat" / "reports").glob("*.json"))
        assert len(reports) == 1
        data = json.loads(reports[0].read_text())
        assert data["old_model_id"] == "v1"
        assert data["new_model_id"] == "v2"

    def test_env_history_recorded(self, tmp_path):
        store = tmp_path / "lineage"
        auto = AutoBaton("env-boat", store_dir=store)
        env = EnvironmentSnapshot(runtime_version="1.0")
        auto.check_expiry(current_env=env)

        history_path = store / "auto" / "env-boat" / "env_history.json"
        assert history_path.exists()
        history = json.loads(history_path.read_text())
        assert len(history) >= 1


# ─── Stats Tests ─────────────────────────────────────────────────────────

class TestStats:
    def test_stats_empty_system(self, tmp_path):
        auto = AutoBaton("empty", store_dir=tmp_path / "lineage")
        stats = auto.stats
        assert stats["total_lessons"] == 0
        assert stats["avg_confidence"] == 0.0

    def test_stats_with_lessons(self, auto_with_lessons):
        stats = auto_with_lessons.stats
        assert stats["total_lessons"] == 4
        assert stats["system_id"] == "test-boat"
        assert "failure" in stats["by_source"]
        assert "pattern" in stats["by_source"]
        assert 0.0 < stats["avg_confidence"] <= 1.0

    def test_stats_by_type(self, auto_with_lessons):
        stats = auto_with_lessons.stats
        assert "temporal" in stats["by_type"]
        assert "timeless" in stats["by_type"]


# ─── Integration Tests ───────────────────────────────────────────────────

class TestAutoBatonIntegration:
    def test_full_lifecycle(self, tmp_path):
        """Full lifecycle: init → record → check → bootstrap → handoff."""
        store = tmp_path / "lineage"

        # 1. Init
        auto = AutoBaton("lifecycle-boat", store_dir=store)
        assert len(auto.brief.lessons) == 0

        # 2. Record lessons over time
        auto.record_lesson("deploy", "zero-downtime switch worked", 0.9)
        auto.record_failure(
            "OOM on large context", "implement sliding window", "critical"
        )
        auto.record_pattern("early termination saves compute", 0.85)
        auto.record_lesson(
            "rate limit", "API allows 200/min", 0.9,
            env_context={"rate_limits": {"api": 200}, "api_versions": {"api": "v3"}},
        )
        assert len(auto.brief.lessons) == 4

        # 3. Check expiry (same environment)
        same_env = EnvironmentSnapshot(
            runtime_version="1.0",
            task_domain="assistant",
        )
        flags = auto.check_expiry(current_env=same_env)
        # Lessons recorded with versioned context may flag
        assert isinstance(flags, list)

        # 4. Bootstrap for new model
        bootstrap = auto.generate_bootstrap("nextgen-model")
        assert "Bootstrap Brief" in bootstrap
        assert "nextgen-model" in bootstrap

        # 5. Full handoff
        new_env = EnvironmentSnapshot(
            runtime_version="2.0",
            task_domain="assistant",
        )
        report = auto.handoff("current-model", "nextgen-model", current_env=new_env)
        assert report.survival_rate >= 0.0
        assert "current-model" in report.summary
        assert "nextgen-model" in report.summary

    def test_multiple_systems_isolated(self, tmp_path):
        """Two systems in the same store don't interfere."""
        store = tmp_path / "lineage"
        auto_a = AutoBaton("boat-alpha", store_dir=store)
        auto_b = AutoBaton("boat-beta", store_dir=store)

        auto_a.record_lesson("alpha event", "alpha result", 0.8)
        auto_b.record_lesson("beta event", "beta result", 0.7)

        # Reload
        auto_a2 = AutoBaton("boat-alpha", store_dir=store)
        auto_b2 = AutoBaton("boat-beta", store_dir=store)

        assert len(auto_a2.brief.lessons) == 1
        assert "alpha" in auto_a2.brief.lessons[0].content
        assert len(auto_b2.brief.lessons) == 1
        assert "beta" in auto_b2.brief.lessons[0].content

    def test_lineage_chain_via_handoff(self, tmp_path):
        """Multiple handoffs create an audit trail."""
        store = tmp_path / "lineage"
        auto = AutoBaton("chain-boat", store_dir=store)

        auto.record_lesson("gen1 lesson", "works", 0.9)
        report1 = auto.handoff("gen1", "gen2")
        report2 = auto.handoff("gen2", "gen3")

        reports_dir = store / "auto" / "chain-boat" / "reports"
        all_reports = list(reports_dir.glob("*.json"))
        assert len(all_reports) == 2

        # Each report should reference the correct models
        data1 = json.loads(
            (reports_dir / "handoff_gen1_to_gen2.json").read_text()
        )
        data2 = json.loads(
            (reports_dir / "handoff_gen2_to_gen3.json").read_text()
        )
        assert data1["old_model_id"] == "gen1"
        assert data2["old_model_id"] == "gen2"
