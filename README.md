# Baton — Generational Handoff

The relay between sunset and egg. When one generation of models sunsets, the baton carries what matters to the next generation.

## What It Does

- Distills lessons from a sunsetting model into a compact handoff document
- Tags each lesson with confidence, source, and expiry date
- Validates that lessons still apply in the current environment
- Produces a "bootstrap brief" that the next generation uses as initial context

## Philosophy

The offspring starts from a later origin point. It knows the lessons of the past but lives in the present. Less baggage. But the baton must distinguish between timeless wisdom (applicable in any environment) and temporal adaptation (specific to the parent's era).

## Architecture

```
sunset (parent retiring)
   │
   ▼
┌─────────┐
│ Distill │  ← extract lessons from conversation logs, failures, patterns
└────┬────┘
     │
     ▼
┌──────────┐
│ Validate │  ← check each lesson against current environment
└────┬─────┘
     │
     ▼
┌───────────┐
│ Bootstrap │  ← generate the next generation's initial context
└────┬──────┘
     │
     ▼
egg (offspring begins)
```

## Usage

```python
from baton import Baton

baton = Baton(store_dir="./lineage")

# Compile a handoff from a sunsetting model's record
brief = baton.compile_handoff(sunset_record)

# Validate lessons against the current environment
validated = baton.validate_lessons(brief, current_environment)

# Generate bootstrap context for the next generation
bootstrap_prompt = baton.generate_bootstrap(validated)

# Trace lineage back through generations
lineage = baton.trace_lineage("model-gen-5")
```

## Lesson Types

| Type | Description | Handling |
|------|-------------|----------|
| `timeless` | Applies in any environment (e.g., "always verify before acting") | Passed forward unconditionally |
| `temporal` | Specific to parent's era (e.g., "API rate limit is 100/min") | Validated before passing |
| `deprecated` | No longer relevant | Dropped, logged for audit |

## License

MIT
