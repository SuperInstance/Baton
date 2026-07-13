# Baton — Generational Handoff for Model Lifecycle

> The relay between sunset and egg. When one generation of models sunsets, the baton carries what matters to the next.

[![Python](https://img.shields.io/python/required-version-toml?toml=pyproject.toml)](https://python.org)
[![License](https://img.shields.io/github/license/SuperInstance/baton)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-61%20passing-brightgreen)](tests/)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)]()

Models don't live forever. They get deprecated, decommissioned, replaced by newer generations. When a model sunsets, everything it learned — the hard-won lessons about your specific users, your domain quirks, your operational gotchas — risks dying with it.

**Baton solves this.** It's a real tool — not an essay, not a framework, not a whitepaper. You install it, you run it, and it manages the generational handoff for your AI system.

## What It Does

Baton operates in two modes:

### Manual Mode (`Baton`)

Takes a model's lifecycle record — conversation logs, failure patterns, operational adjustments, user feedback — and distills it into structured `Lesson` objects. Each lesson has a type (`timeless`, `temporal`, `deprecated`), a confidence score, a source citation, and environment context. The validator checks each lesson against the current environment, and the bootstrap generator produces a markdown brief for the next generation's system prompt.

### Automatic Mode (`AutoBaton`)

Sits alongside your running AI system and manages the lifecycle continuously:
- **Records lessons** from operational events as they happen
- **Flags stale knowledge** when the environment shifts (API changes, domain changes, runtime upgrades)
- **Generates bootstrap context** when you upgrade to a new model
- **Executes end-to-end handoffs** with testing and full audit trail

### CLI Mode

```bash
baton init --system-id my-boat
baton record --event "quota check" --outcome "blocked 3 overages" --confidence 0.9
baton record-failure --what "timeout on API" --correction "add retry backoff" --severity high
baton record-pattern --pattern "batch requests reduce latency" --confidence 0.85
baton check-expiry
baton bootstrap --new-model llama-3.3-70b
baton handoff --old glm-5.2 --new llama-3.3-70b
baton stats
baton list
baton export -o brief.json
```

## Install

```bash
pip install baton-handoff
```

For development:

```bash
git clone https://github.com/SuperInstance/baton.git
cd baton
pip install -e ".[dev]"
pytest tests/ -v
```

## Quick Start

### Automatic Lifecycle (the easy path)

```python
from baton import AutoBaton

# Initialize — creates a persistent state directory
auto = AutoBaton("my-boat", store_dir="./lineage")

# Record lessons as your system runs
auto.record_lesson("quota check", "blocked 3 overages", 0.9, tags=["ops"])
auto.record_failure("timeout on API", "add retry with backoff", severity="high")
auto.record_pattern("batch requests reduce latency", 0.85)

# Check if accumulated wisdom is still valid
flags = auto.check_expiry()
for flag in flags:
    print(f"⚠ {flag.lesson.content}: {flag.reason}")

# Generate bootstrap context for a model upgrade
bootstrap = auto.generate_bootstrap("llama-3.3-70b")
print(bootstrap)

# Full handoff — validates, bootstraps, tests, reports
report = auto.handoff("glm-5.2", "llama-3.3-70b")
print(report.summary)
# → Handoff glm-5.2 → llama-3.3-70b: 8 carried, 2 stale, 1 dropped (73% survival)
```

### Manual Lifecycle (full control)

```python
from baton import Baton, EnvironmentSnapshot

baton = Baton(store_dir="./lineage")

# Compile handoff from sunset record
brief = baton.compile_handoff({
    "model_id": "aurora-v4",
    "generation": 4,
    "conversation_logs": [...],
    "failure_modes": [...],
    "successful_patterns": [...],
    "fence_triggers": [...],
})

# Validate against current environment
env = EnvironmentSnapshot(
    runtime_version="5.0.0",
    model_family="aurora",
    api_versions={"main_api": "v3"},
    rate_limits={"main_api": 200},
)
validated = baton.validate_lessons(brief, env)

print(f"Active: {len(validated.active_lessons)}")
print(f"Stale: {len(validated.stale_lessons)}")
print(f"Deprecated: {len(validated.deprecated_lessons)}")
print(f"Survival: {validated.survival_rate:.0%}")

# Generate bootstrap for next generation
bootstrap_prompt = baton.generate_bootstrap(validated)

# Trace lineage
lineage = baton.trace_lineage("aurora-v4")
for node in lineage:
    print(f"Gen {node.generation}: {node.model_id}")
```

### CLI

```bash
# Initialize
$ baton init --system-id my-boat
✓ Initialized baton system: my-boat
  Store: /abs/path/lineage
  Baton ID: auto-my-boat-a1b2c3d4

# Record events
$ baton record --system-id my-boat --event "quota check" --outcome "blocked 3 overages" --confidence 0.9
✓ Recorded lesson:
  [timeless] quota check: blocked 3 overages [my-boat]
            confidence: 90% ▓▓▓▓░ | source: feedback | assessment: unevaluated

# See stats
$ baton stats --system-id my-boat
  System: my-boat
  Total lessons: 4
  Avg confidence: 82%
  
  By source:
            feedback: 2
            failure: 1
            pattern: 1

# Full handoff
$ baton handoff --system-id my-boat --old glm-5.2 --new llama-3.3-70b
══════════════════════════════════════════════
  GENERATIONAL HANDOFF COMPLETE
══════════════════════════════════════════════
  glm-5.2 → llama-3.3-70b
────────────────────────────────────────────
  Lessons carried:   3
  Lessons stale:     1
  Lessons dropped:   0
  Survival rate:     75%
══════════════════════════════════════════════
```

## Lesson Types

| Type | Description | Handling | Example |
|------|-------------|----------|---------|
| `timeless` | Applies in any environment | Passed forward unconditionally | "Always verify checksums before processing" |
| `temporal` | Specific to parent's era | Validated before passing | "API rate limit is 100/min" |
| `deprecated` | No longer relevant | Dropped, logged for audit | "Use v2 endpoint (v3 now exists)" |

AutoBaton infers types automatically:
- **Fence triggers** → `timeless` (conservation laws don't expire)
- **Failures** → `temporal` (environment-specific by nature)
- **Patterns/feedback** → `timeless` unless context has versioned keys, then `temporal`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AutoBaton (CLI)                         │
│                                                              │
│  record_lesson    record_failure    record_pattern           │
│       │                │                  │                  │
│       └────────────────┼──────────────────┘                  │
│                        ▼                                     │
│              ┌─────────────────┐                             │
│              │  HandoffBrief   │  ← accumulated lessons      │
│              │   (persistent)  │     with confidence + type  │
│              └────────┬────────┘                             │
│                       │                                      │
│    ┌──────────────────┼──────────────────┐                   │
│    │                  │                  │                   │
│    ▼                  ▼                  ▼                   │
│ check_expiry    bootstrap         handoff                    │
│    │                │                  │                     │
│    ▼                ▼                  ▼                     │
│ ExpiryFlags    Bootstrap Brief   HandoffReport               │
│ (stale?)       (for new model)   (full audit)                │
│                                                              │
│                    ┌─────────────┐                           │
│                    │ Environment │                           │
│                    │  Snapshot   │  ← what changed?          │
│                    └─────────────┘                           │
└─────────────────────────────────────────────────────────────┘

sunset (parent retiring)
   │
   ▼
┌─────────────┐
│  Distiller  │  ← extract lessons from logs, failures,
└──────┬──────┘     patterns, fence triggers
       │
       ▼
┌─────────────┐
│ HandoffBrief│  ← structured lessons with confidence + type
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Validator  │  ← check each lesson against current environment
└──────┬──────┘     (API versions, runtime, domain, rate limits)
       │
       ▼
┌──────────────┐
│ ValidatedBrief│ ← active + stale + deprecated
└──────┬───────┘
       │
       ▼
┌───────────────┐
│   Bootstrap   │  ← structured markdown for the
│  Generator    │     next generation's system prompt
└──────┬────────┘
       │
       ▼
egg (offspring begins with inherited wisdom)
```

## API Reference

### `AutoBaton`

```python
class AutoBaton:
    def __init__(self, system_id: str, store_dir: str = "./lineage")

    # Recording
    def record_lesson(self, event: str, outcome: str, confidence: float, *,
                      source: str = "feedback", tags: list[str] | None = None,
                      env_context: dict | None = None) -> Lesson
    def record_failure(self, what_failed: str, correction: str,
                       severity: str = "medium") -> Lesson
    def record_pattern(self, pattern: str, confidence: float = 0.8) -> Lesson

    # Lifecycle
    def check_expiry(self, current_env: EnvironmentSnapshot | None = None) -> list[ExpiryFlag]
    def generate_bootstrap(self, new_model_id: str,
                          current_env: EnvironmentSnapshot | None = None) -> str
    def handoff(self, old_model, new_model, *,
                test_prompts: list[str] | None = None) -> HandoffReport

    # Properties
    @property
    def stats(self) -> dict
```

### `Baton` (manual mode)

```python
class Baton:
    def __init__(self, store_dir: str = "./lineage")
    def compile_handoff(self, sunset_record: dict,
                        parent_brief_id: str | None = None) -> HandoffBrief
    def validate_lessons(self, brief: HandoffBrief,
                         env: EnvironmentSnapshot) -> ValidatedBrief
    def generate_bootstrap(self, validated: ValidatedBrief) -> str
    def trace_lineage(self, model_id: str) -> list[HandoffBrief]
```

### `HandoffReport`

```python
@dataclass
class HandoffReport:
    old_model_id: str
    new_model_id: str
    bootstrap_brief: str
    lessons_carried: int
    lessons_dropped: int
    lessons_stale: int
    survival_rate: float
    test_results: dict[str, bool]

    @property
    def summary(self) -> str
    def to_dict(self) -> dict
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `baton init` | Initialize a new baton system |
| `baton record` | Record a lesson from an operational event |
| `baton record-failure` | Record a failure and correction |
| `baton record-pattern` | Record a successful pattern |
| `baton check-expiry` | Flag potentially stale lessons |
| `baton bootstrap` | Generate bootstrap context for a new model |
| `baton handoff` | Execute full generational handoff |
| `baton stats` | Show accumulated wisdom statistics |
| `baton list` | List all recorded lessons |
| `baton show` | Show current brief details |
| `baton export` | Export current brief as JSON |

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

61 tests covering: lesson model, distiller, validator, bootstrap generator, lineage store, manual baton integration, and the full AutoBaton lifecycle (recording, expiry checking, bootstrap generation, handoff with model runners, persistence, multi-system isolation, lineage chains).

## Philosophy

In the [Egg and the Organism](https://github.com/SuperInstance/AI-Writings/blob/main/THE_EGG_AND_THE_ORGANISM.md) model, the baton is the moment between SUNSET and EGG — the generational handoff. A sunsetting model doesn't just disappear. It passes distilled wisdom to its successor: proven patterns, hard-won corrections, conservation fence triggers.

But wisdom has a shelf life. What was true when the parent was hatched may be false when the offspring is hatched. The environment changed. The APIs changed. The tools evolved. The baton carries wisdom, but validates it against the present before passing it forward.

**The tension:** carry the wisdom, not the baggage. The offspring starts from a later origin point — it knows the lessons of the past but lives in the present.

### The Egg Model

```
EGG → COMPETE → SURVIVE → BREED → SUNSET → ARCHIVE
                                      │
                                   BATON
                                      │
                                      ▼
                                    EGG (next generation)
```

- **EGG** — model placed in environment, self-assembly begins
- **COMPETE** — evaluated on ethos (efficiency), pathos (human value), logos (reasoning)
- **SURVIVE** — proves value over time, handles edge cases
- **BREED** — successful traits contribute to next generation via baton
- **SUNSET** — retired with dignity, patterns become training data
- **ARCHIVE** — complete record preserved, lineage tracked, contributions credited

The baton is the relay. It separates **timeless wisdom** from **temporal adaptation** so the offspring inherits the wisdom without the outdated assumptions.

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
