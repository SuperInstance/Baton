# Baton — Generational Handoff

> The relay between sunset and egg. When one generation of models sunsets, the baton carries what matters to the next.

[![Python](https://img.shields.io/python/required-version-toml?toml=pyproject.toml)](https://python.org)
[![License](https://img.shields.io/github/license/SuperInstance/baton)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](tests/)

Models don't live forever. They get deprecated, decommissioned, replaced by newer generations. When a model sunsets, everything it learned — the hard-won lessons about your specific users, your domain quirks, your operational gotchas — risks dying with it. Baton solves this by distilling a sunsetting model's accumulated wisdom into a structured handoff brief, validating each lesson against the current environment, and producing a bootstrap document for the next generation.

## What It Does

Baton takes a model's lifecycle record — conversation logs, failure patterns, operational adjustments, user feedback — and distills it into a set of `Lesson` objects. Each lesson has a type (`timeless`, `temporal`, `deprecated`), a confidence score, a source citation, and an optional expiry date. The distiller uses pattern analysis to extract recurring themes: things the model consistently got right, things it consistently got wrong, and situational adaptations it developed over time.

The validator then checks each lesson against the current environment. A lesson like "the API rate limit is 100/min" is `temporal` — it might have changed. A lesson like "always verify file checksums before processing" is `timeless` — it applies in any environment. Lessons that no longer apply are marked `deprecated` and dropped. The result is a `ValidatedBrief` with only the lessons worth carrying forward.

Finally, the bootstrap generator produces a structured markdown brief that the next generation uses as initial context. The brief groups active lessons by type, includes stale lessons as cautionary context, and closes with a clear directive: *"These lessons are your inheritance, not your constraints."*

## Install

```bash
pip install baton-handoff
```

For development:

```bash
git clone https://github.com/SuperInstance/baton.git
cd baton
pip install -e ".[dev]"
```

## Quick Start

```python
from baton import Baton, HandoffBrief, Lesson, LessonType

baton = Baton(store_dir="./lineage")

# Compile a handoff from a sunsetting model's record
brief = baton.compile_handoff(
    model_id="assistant-gen-4",
    generation=4,
    records_path="./logs/gen-4/",
)

# Inspect the distilled lessons
for lesson in brief.lessons:
    print(f"[{lesson.type}] {lesson.content}")
    print(f"  confidence: {lesson.confidence:.0%}")
    print(f"  source: {lesson.source}")

# Validate lessons against the current environment
env_snapshot = baton.capture_environment()
validated = baton.validate_lessons(brief, env_snapshot)

print(f"Active: {len(validated.active_lessons)}")
print(f"Stale: {len(validated.stale_lessons)}")
print(f"Deprecated: {len(validated.deprecated_lessons)}")

# Generate bootstrap context for the next generation
bootstrap_prompt = baton.generate_bootstrap(validated)
print(bootstrap_prompt)

# Trace lineage back through handoffs
lineage = baton.trace_lineage("assistant-gen-4")
for node in lineage:
    print(f"Gen {node.generation}: {node.model_id} ({node.active_lessons} active lessons)")
```

## Lesson Types

| Type | Description | Handling | Example |
|------|-------------|----------|---------|
| `timeless` | Applies in any environment | Passed forward unconditionally | "Always verify checksums before processing" |
| `temporal` | Specific to parent's era | Validated before passing | "API rate limit is 100/min" |
| `deprecated` | No longer relevant | Dropped, logged for audit | "Use v2 endpoint (v3 now exists)" |

## Architecture

```
sunset (parent retiring)
   │
   ▼
┌─────────────┐
│  Distiller  │  ← extract lessons from conversation logs,
└──────┬──────┘     failure patterns, operational adjustments
       │
       ▼
┌─────────────┐
│ HandoffBrief│  ← structured lesson set with confidence scores
└──────┬──────┘     and source citations
       │
       ▼
┌─────────────┐
│  Validator  │  ← check each lesson against current environment
└──────┬──────┘     snapshot (API versions, infra changes, etc.)
       │
       ▼
┌──────────────┐
│ ValidatedBrief│ ← active lessons + stale + deprecated
└──────┬───────┘
       │
       ▼
┌───────────────┐
│   Bootstrap   │  ← generate structured markdown for the
│  Generator    │     next generation's initial context
└──────┬────────┘
       │
       ▼
egg (offspring begins with inherited wisdom)
```

## API Reference

### `Baton`

```python
class Baton:
    def __init__(self, store_dir: str = "./lineage")

    # Distillation
    def compile_handoff(self, model_id: str, generation: int,
                        records_path: str | Path) -> HandoffBrief

    # Validation
    def capture_environment(self) -> EnvironmentSnapshot
    def validate_lessons(self, brief: HandoffBrief,
                         env: EnvironmentSnapshot) -> ValidatedBrief

    # Bootstrap
    def generate_bootstrap(self, validated: ValidatedBrief) -> str

    # Lineage
    def trace_lineage(self, model_id: str) -> list[LineageNode]
    def save_brief(self, brief: HandoffBrief) -> Path
    def load_brief(self, brief_id: str) -> HandoffBrief
```

### `Lesson`

```python
@dataclass
class Lesson:
    content: str               # the lesson text
    type: LessonType           # TIMELESS, TEMPORAL, DEPRECATED
    confidence: float          # 0.0-1.0
    source: str                # where this lesson was extracted from
    expiry_date: str | None    # ISO date for temporal lessons
    metadata: dict[str, Any]   # arbitrary metadata
```

### `HandoffBrief` and `ValidatedBrief`

```python
@dataclass
class HandoffBrief:
    id: str                    # UUID
    model_id: str
    generation: int
    lessons: list[Lesson]
    compiled_at: str           # ISO timestamp
    parent_brief_id: str | None

@dataclass
class ValidatedBrief:
    handoff: HandoffBrief
    active_lessons: list[Lesson]      # passed validation
    stale_lessons: list[Lesson]       # might not apply
    deprecated_lessons: list[Lesson]  # confirmed irrelevant
    validation_notes: dict[str, ExpiryAssessment]
```

### `EnvironmentSnapshot`

```python
@dataclass
class EnvironmentSnapshot:
    captured_at: str           # ISO timestamp
    api_versions: dict[str, str]
    active_services: list[str]
    config_values: dict[str, Any]
    changes_since_last: list[str]  # diff from previous snapshot
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Philosophy

In animal husbandry, generational knowledge transfer happens through genetics and (in working animals) through trained responses that get refined over time. In AI, we have neither mechanism by default — each new model starts tabula rasa. Baton is the artificial equivalent: a method for passing hard-won operational wisdom from parent to offspring without carrying forward outdated assumptions.

The key insight is distinguishing **timeless wisdom** from **temporal adaptation**. "Always verify before acting" is timeless — it applied a century ago and will apply a century from now. "The rate limit is 100/min" is temporal — it's a fact about a specific API at a specific time. Baton separates these categories so the offspring starts from a later origin point: it inherits the wisdom without the baggage.

This is part of the Working Animal Architecture paradigm — specifically the lifecycle layer that connects [lineage tracking](https://github.com/SuperInstance/lineage-tracker) (who begot whom) with [breed registries](https://github.com/SuperInstance/breed-registry) (what each breed is good at). Baton handles the handoff between generations.

For more, see [AI-Writings](https://github.com/SuperInstance/AI-Writings).

## Ecosystem

| Repo | Role |
|------|------|
| **[baton](https://github.com/SuperInstance/baton)** | **This repo** — generational handoff |
| [lineage-tracker](https://github.com/SuperInstance/lineage-tracker) | Provenance records (baton uses lineage data) |
| [pedigree](https://github.com/SuperInstance/pedigree) | Bloodline tracking with diversity metrics |
| [breed-registry](https://github.com/SuperInstance/breed-registry) | Model selection for the next generation |
| [vetcheck](https://github.com/SuperInstance/vetcheck) | Health monitoring (informs sunset decisions) |

## License

MIT — see [LICENSE](LICENSE).
