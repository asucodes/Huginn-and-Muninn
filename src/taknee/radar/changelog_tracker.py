"""Radar changelog tracker — detects new free models and new providers.

Compares current OpenRouter + provider model catalogs against a local
snapshot to detect newly added zero-cost models and surface them as Deals.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

import httpx

from ..swarm.radar import FreeModel, Radar

SNAPSHOT_FILE = Path.home() / ".taknee" / "model_snapshot.json"


@dataclass
class ModelDelta:
    """Represents a model that appeared new since last snapshot."""
    model_id: str
    provider: str
    name: str
    is_free: bool
    context_window: int
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChangelogTracker:
    """Tracks provider model catalog changes to detect new free models."""

    def __init__(self, radar: Radar | None = None, snapshot_path: Path = SNAPSHOT_FILE):
        self.radar = radar or Radar()
        self.snapshot_path = snapshot_path
        self._snapshot: dict[str, Any] = self._load_snapshot()

    def _load_snapshot(self) -> dict[str, Any]:
        if self.snapshot_path.exists():
            try:
                return json.loads(self.snapshot_path.read_text())
            except Exception:
                pass
        return {"model_ids": [], "saved_at": 0.0}

    def _save_snapshot(self, model_ids: list[str]) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps({
            "model_ids": model_ids, "saved_at": time.time()
        }))

    def detect_new_models(self) -> list[ModelDelta]:
        """Returns models that are newly free since last snapshot."""
        current_models = self.radar.scan_all()
        current_ids = {m.id for m in current_models if m.is_free}
        previous_ids = set(self._snapshot.get("model_ids", []))

        new_ids = current_ids - previous_ids
        self._save_snapshot(list(current_ids))
        self._snapshot = {"model_ids": list(current_ids), "saved_at": time.time()}

        deltas: list[ModelDelta] = []
        for m in current_models:
            if m.id in new_ids:
                deltas.append(ModelDelta(
                    model_id=m.id, provider=m.provider,
                    name=m.name, is_free=m.is_free,
                    context_window=m.context_window,
                ))
        return deltas
