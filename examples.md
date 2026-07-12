# Examples — Baton Generational Handoff

> Real-world patterns for passing knowledge between model generations.

## Example 1: Basic Generational Handoff

When a model is being deprecated, distill its lessons for the replacement.

```python
from baton import Baton, Lesson, LessonType

baton = Baton(store_dir="./lineage")

# Compile a handoff from the outgoing model's logs
brief = baton.compile_handoff(
    model_id="assistant-gen-4",
    generation=4,
    records_path="./logs/gen-4/",
)

print(f"Distilled {len(brief.lessons)} lessons from gen-4")
for lesson in brief.lessons[:5]:
    print(f"  [{lesson.type}] {lesson.content}")
```

## Example 2: Lesson Validation Against Current Environment

Not all lessons survive generational transfer. The validator checks each one.
```python
# Capture the current environment state
env = baton.capture_environment()

# Validate each lesson
validated = baton.validate_lessons(brief, env)

print(f"Active (carry forward):     {len(validated.active_lessons)}")
print(f"Stale (needs re-check):     {len(validated.stale_lessons)}")
print(f"Deprecated (drop):          {len(validated.deprecated_lessons)}")

# Inspect deprecated lessons
for lesson in validated.deprecated_lessons:
    print(f"  ✗ {lesson.content}")
    print(f"    Reason: {lesson.deprecation_reason}")
```

## Example 3: Generating a Bootstrap Brief for the Next Generation

Produce a structured markdown document that becomes the new model's initial context.

```python
validated = baton.validate_lessons(brief, env)
bootstrap = baton.generate_bootstrap(validated)

# The bootstrap is a markdown document
print(bootstrap[:500])
# # Handoff Brief: assistant-gen-4 → assistant-gen-5
#
# ## Active Lessons
#
# ### Timeless
# - Always verify file checksums before processing
# - Log every API call with timestamp and duration
# - Never assume the database schema is stable
#
# ### Temporal
# - Rate limit is currently 100/min (verify on first call)
# ...

# Save it for the deployment pipeline
with open("gen5_bootstrap.md", "w") as f:
    f.write(bootstrap)
```

## Example 4: Tracing Lineage Across Multiple Generations

Follow the chain of handoffs backwards to understand the heritage.

```python
lineage = baton.trace_lineage("assistant-gen-5")

for node in lineage:
    print(f"Gen {node.generation}: {node.model_id}")
    print(f"  Active lessons:  {node.active_lessons}")
    print(f"  Handoff date:    {node.handoff_date}")
    print(f"  Status:          {node.status}")
    if node.parent:
        print(f"  Inherited from: {node.parent}")
    print()
```

## Example 5: Manual Lesson Curation

Sometimes you need to hand-craft lessons for edge cases the distiller misses.

```python
from baton import Baton, HandoffBrief, Lesson, LessonType
from datetime import date

baton = Baton(store_dir="./lineage")

# Manually define lessons for a custom handoff
lessons = [
    Lesson(
        type=LessonType.TIMELESS,
        content="Always cite sources when making factual claims in responses.",
        confidence=0.98,
        source="manual:ops-team",
    ),
    Lesson(
        type=LessonType.TEMPORAL,
        content="The CRM API uses OAuth2 with PKCE — client secret rotation is quarterly.",
        confidence=0.90,
        source="ops-log:2026-Q2",
        expiry=date(2026, 10, 1),
    ),
    Lesson(
        type=LessonType.DEPRECATED,
        content="Use the v2 messaging endpoint.",
        confidence=1.0,
        source="deprecated:v3-released",
    ),
]

brief = HandoffBrief(
    model_id="assistant-gen-4",
    generation=4,
    lessons=lessons,
)

# Validate and generate bootstrap
env = baton.capture_environment()
validated = baton.validate_lessons(brief, env)
bootstrap = baton.generate_bootstrap(validated)

print(f"Manually curated brief: {len(validated.active_lessons)} active lessons")
```
