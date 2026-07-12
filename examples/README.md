# Baton Examples

## handoff_example.py

Demonstrates a full generational handoff cycle:
- **Aurora v4** (generation 4) is sunsetting
- Baton distills lessons from its sunset record
- Lessons are validated against Aurora v5's environment
- A bootstrap brief is generated for the next generation

Run with:

```bash
pip install -e ".[dev]"
python examples/handoff_example.py
```

### What to expect

The example shows:
1. **7 lessons** extracted from v4's record (conversations, failures, patterns, fence triggers)
2. **Validation** — the legacy auth API lesson becomes stale (v1 → v2), the context overflow lesson expires (v5 has 128k context)
3. **Timeless lessons survive** — decomposition strategy, clarifying questions, conservation fences
4. **Bootstrap brief** — structured handoff document that Aurora v5 uses as initial context
