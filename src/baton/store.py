"""Lineage store — JSON-based lineage chain for baton handoffs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LineageStore:
    """Stores handoff briefs as JSON files in a lineage chain.

    Each brief is saved as a JSON file in the store directory.
    The chain is maintained via parent_brief_id pointers.
    """

    def __init__(self, store_dir: str | Path = "./lineage"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, brief) -> str:
        """Save a handoff brief to the store.

        Returns the path to the saved file.
        """
        path = self.store_dir / f"{brief.id}.json"
        path.write_text(
            json.dumps(brief.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(path)

    def load(self, brief_id: str) -> dict[str, Any] | None:
        """Load a brief by ID. Returns None if not found."""
        path = self.store_dir / f"{brief_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_briefs(self) -> list[dict[str, Any]]:
        """List all stored briefs, newest first."""
        files = sorted(self.store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [json.loads(f.read_text(encoding="utf-8")) for f in files]

    def trace_lineage(self, model_id: str) -> list:
        """Trace the baton chain for a given model.

        Follows parent_brief_id pointers back through generations.
        Returns a list of HandoffBrief objects (requires import to avoid circular).
        """
        from . import HandoffBrief

        # Find the most recent brief for this model
        all_briefs = self.list_briefs()
        briefs_by_id = {b["id"]: b for b in all_briefs}

        # Find briefs where this model is the recipient (next gen)
        # or the originator
        chain: list[HandoffBrief] = []
        seen: set[str] = set()

        # Start with briefs compiled by this model
        candidates = [b for b in all_briefs if b.get("model_id") == model_id]
        if not candidates:
            return []

        # Pick the most recent
        current = max(candidates, key=lambda b: b.get("generation", 0))

        while current and current["id"] not in seen:
            seen.add(current["id"])
            chain.append(HandoffBrief.from_dict(current))

            parent_id = current.get("parent_brief_id")
            if parent_id and parent_id in briefs_by_id:
                current = briefs_by_id[parent_id]
            else:
                current = None

        return chain
