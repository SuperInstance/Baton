# Baton — Generational Handoff for Model Lifecycle

> The relay between sunset and egg. When one generation of models sunsets, the baton carries what matters forward.

When a model has run its course — too expensive, too slow, superseded — you retire it. But it learned things. It failed in instructive ways. It discovered patterns that work. **Baton** distills that hard-won experience into a structured handoff brief, validates which lessons still apply, and generates bootstrap context for the next generation.

## Why It Exists

Models are replaced, not immortal. The institutional knowledge they accumulate shouldn't die with them. Traditional approaches dump conversation logs on the replacement model, hoping it'll figure out what matters. Baton treats generational handoff as a first-class engineering problem:

- **Distill** — Extract lessons from conversation logs, failure modes, successful patterns, and conservation fence triggers
- **Validate** — Check each lesson against the current environment. Does this still apply?
- **Bootstrap** — Generate a structured brief the next generation can parse and prioritize

The offspring starts from a later origin point. It knows the lessons of the past but lives in the present. Less baggage, more momentum.

## Installation

```bash
pip install baton-handoff
```

Requires Python 3.10+.

## Quick Start

```python
from baton import Baton, EnvironmentSnapshot

baton = Baton(store_dir="./lineage")

# 1. Compile a handoff from a sunsetting model's experience
sunset_record = {
    "model_id": "gpt-4-deployment-7",
    "generation": 7,
    "conversation_logs": [
        {
            "lesson": "Users frequently ask follow-up clarifications when summaries exceed 500 tokens.",
            "confidence": 0.82,
            "tags": ["ux", "summarization"],
        },
    ],
    "failure_modes": [
        {
            "what": "Hallucinated API method names when context > 100k tokens",
            "correction": "Always verify method signatures via tool call before emitting code",
            "severity": "critical",
        },
    ],
    "successful_patterns": [
        {
            "lesson": "Chain-of-thought before tool selection improves accuracy by ~15%",
            "confidence": 0.88,
        },
    ],
    "fence_triggers": [
        {
            "rule": "budget_decay: max 4096 tokens per turn",
            "reason": "Cost control — enforced by conservation fence",
        },
    ],
}

brief = baton.compile_handoff(sunset_record)
print(f"Compiled {len(brief.lessons)} lessons into {brief.id}")

# 2. Validate against the new generation's environment
env = EnvironmentSnapshot(
    runtime_version="2.0",
    model_family="gpt-4o",
    task_domain="customer-support",
    conservation_version="2.1",
    api_versions={"openai": "2024-12-01"},
)

validated = baton.validate_lessons(brief, env)
print(f"Active: {len(validated.active_lessons)}")
print(f"Stale: {len(validated.stale_lessons)}")
print(f"Deprecated: {len(validated.deprecated_lessons)}")
print(f"Survival rate: {validated.survival_rate:.0%}")

# 3. Generate bootstrap context for the replacement model
bootstrap_prompt = baton.generate_bootstrap(validated)
# Feed `bootstrap_prompt` as system prompt to the new model

# 4. Trace lineage across generations
lineage = baton.trace_lineage("gpt-4-deployment-7")
for ancestor_brief in lineage:
    print(f"Gen {ancestor_brief.generation}: {ancestor_brief.id} ({len(ancestor_brief.lessons)} lessons)")
```

## Architecture

```
sunset (parent retiring)
   │
   ▼
┌─────────────┐
│  Distiller  │  ← extract lessons from 4 sources:
│             │     conversation logs, failure modes,
│             │     successful patterns, fence triggers
└──────┬──────┘
       │  list[Lesson]
       ▼
┌─────────────┐
│  Validator   │  ← check each lesson against
│             │     EnvironmentSnapshot
└──────┬──────┘
       │  active / stale / deprecated
       ▼
┌──────────────┐
│  Bootstrap   │  ← generate structured brief
│  Generator   │     for the next generation
└──────┬───────┘
       │
       ▼
egg (offspring begins with inherited wisdom)
```

### Data Flow

1. **`Distiller.distill()`** extracts `Lesson` objects from a sunset record's four sources
2. **`Validator.validate_batch()`** sorts lessons into active / stale / deprecated based on environment drift
3. **`BootstrapGenerator.generate()`** produces a structured markdown brief the new model reads at startup
4. **`LineageStore`** persists each brief as JSON, maintaining the parent-child chain via `parent_brief_id`

## API Reference

### `Baton(store_dir="./lineage")`

The main orchestrator. Creates internal `Distiller`, `Validator`, `BootstrapGenerator`, and `LineageStore` instances.

| Method | Returns | Description |
|--------|---------|-------------|
| `compile_handoff(sunset_record, parent_brief_id=None)` | `HandoffBrief` | Distill a retiring model's experience into a structured brief |
| `validate_lessons(brief, current_environment)` | `ValidatedBrief` | Check which lessons survive the environment transition |
| `generate_bootstrap(validated)` | `str` | Produce the bootstrap system prompt for the next generation |
| `trace_lineage(model_id)` | `list[HandoffBrief]` | Walk the parent chain back through generations |

### `Lesson`

The atomic unit of inherited wisdom.

| Field | Type | Description |
|-------|------|-------------|
| `content` | `str` | The lesson text — what was learned |
| `confidence` | `float` | How strongly held (0.0–1.0) |
| `source` | `str` | `experiment`, `feedback`, `failure`, `pattern`, or `fence_trigger` |
| `environment_context` | `dict` | What was true when learned (versions, limits, etc.) |
| `expiry_assessment` | `ExpiryAssessment` | `unevaluated`, `active`, `stale`, `expired` |
| `lesson_type` | `LessonType` | `timeless`, `temporal`, `deprecated` |
| `is_actionable` | `bool` | Whether this lesson should influence the next generation |

### Lesson Types

| Type | Description | Validation Behavior |
|------|-------------|---------------------|
| `timeless` | Applies in any environment (e.g., "always verify before acting") | Active unless conservation version changed |
| `temporal` | Specific to parent's era (e.g., "rate limit is 100/min") | Full environment diff — stale if 1 thing changed, expired if 2+ |
| `deprecated` | No longer relevant | Always expired |

### `EnvironmentSnapshot`

The runtime context of the new generation. Used to validate inherited lessons.

| Field | Type | Description |
|-------|------|-------------|
| `runtime_version` | `str` | Runtime/engine version |
| `model_family` | `str` | Model family (e.g., `"gpt-4o"`) |
| `task_domain` | `str` | Task category |
| `conservation_version` | `str` | Conservation fence policy version |
| `api_versions` | `dict[str, str]` | API versions in use |
| `rate_limits` | `dict[str, int]` | Current rate limits |
| `capabilities` | `list[str]` | Available capabilities |

### `ValidatedBrief`

| Field | Type | Description |
|-------|------|-------------|
| `handoff` | `HandoffBrief` | The original brief |
| `active_lessons` | `list[Lesson]` | Lessons that survived validation |
| `stale_lessons` | `list[Lesson]` | Lessons with one environment change (confidence halved) |
| `deprecated_lessons` | `list[Lesson]` | Lessons with multiple changes (confidence × 0.1) |
| `survival_rate` | `float` | Fraction of lessons that survived |

### `LineageStore`

JSON-file-based lineage persistence. Each brief is saved as `{brief_id}.json` in the store directory.

| Method | Description |
|--------|-------------|
| `save(brief)` | Persist a brief to disk |
| `load(brief_id)` | Load a brief by ID |
| `list_briefs()` | List all briefs, newest first |
| `trace_lineage(model_id)` | Follow `parent_brief_id` pointers to the root |

## Testing

```bash
# Clone and install dev dependencies
git clone https://github.com/SuperInstance/baton.git
cd baton
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=baton --cov-report=term-missing
```

## Ecosystem

Baton is part of **Working Animal Architecture**:

| Repo | Role |
|------|------|
| **`SuperInstance/baton`** | **Generational handoff — this repo** |
| `SuperInstance/whistle` | Intent DSL for declaring working animals |
| `SuperInstance/trawl` | Commercial fishing implementation (proves the paradigm) |
| `SuperInstance/a2ui` | Adaptive interface generation |
| `SuperInstance/shepherds-console` | Operations dashboard |

## Philosophy

The offspring should not inherit the parent's scars — only its wisdom.

Traditional model replacement treats the new model as a blank slate, forcing it to rediscover everything the old model learned through trial and error. This is wasteful and slow. But blindly dumping the parent's entire experience is equally wrong — much of it was specific to the parent's environment, capabilities, and era.

Baton's core insight: **lessons have expiry dates**. A lesson about an API rate limit is temporal — it dies with the old environment. A lesson about always verifying before acting is timeless — it survives any transition. The distiller extracts all lessons; the validator sorts them; the bootstrap generator passes forward only what still matters.

The result: the next generation starts informed, not from scratch, and not burdened with irrelevant baggage.

## License

MIT
