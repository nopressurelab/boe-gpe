"""Persistence of provisions as JSON, one file per publication date."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Iterator

from .util import now_utc, rfc3339

log = logging.getLogger(__name__)

ITEMS_SUBDIR = "items"
STATE_FILE = "state.json"


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.items_dir = self.data_dir / ITEMS_SUBDIR

    # -- reading ---------------------------------------------------------
    def day_path(self, day: dt.date | str) -> Path:
        key = day.isoformat() if isinstance(day, dt.date) else str(day)
        return self.items_dir / f"{key}.json"

    def load_day(self, day: dt.date | str) -> list[dict[str, Any]]:
        path = self.day_path(day)
        if not path.is_file():
            return []
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle).get("items", [])
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read %s: %s", path, exc)
            return []

    def available_days(self) -> list[str]:
        if not self.items_dir.is_dir():
            return []
        return sorted((p.stem for p in self.items_dir.glob("*.json")), reverse=True)

    def iter_items(self, limit_days: int | None = None) -> Iterator[dict[str, Any]]:
        days = self.available_days()
        if limit_days is not None:
            days = days[:limit_days]
        for day in days:
            yield from self.load_day(day)

    def recent_items(self, days: int) -> list[dict[str, Any]]:
        items = list(self.iter_items(limit_days=days))
        items.sort(key=lambda i: (i.get("date", ""), i.get("score", 0)), reverse=True)
        return items

    # -- writing ---------------------------------------------------------
    def merge_day(self, day: str, incoming: list[dict[str, Any]]) -> tuple[int, int]:
        """Merge by id, preserving `first_seen`. Returns (new, total)."""
        existing = {item["id"]: item for item in self.load_day(day)}
        new_count = 0
        for item in incoming:
            previous = existing.get(item["id"])
            if previous is None:
                new_count += 1
            else:
                item["first_seen"] = previous.get("first_seen", item["first_seen"])
            existing[item["id"]] = item
        merged = sorted(existing.values(),
                        key=lambda i: (-float(i.get("score", 0)), i.get("source", "")))
        self.items_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": day,
            "generated_at": rfc3339(now_utc()),
            "count": len(merged),
            "items": merged,
        }
        with self.day_path(day).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        return new_count, len(merged)

    def prune(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (dt.date.today() - dt.timedelta(days=retention_days)).isoformat()
        removed = 0
        for path in self.items_dir.glob("*.json"):
            if path.stem < cutoff:
                path.unlink()
                removed += 1
        return removed

    # -- state -----------------------------------------------------------
    def load_state(self) -> dict[str, Any]:
        path = self.data_dir / STATE_FILE
        if not path.is_file():
            return {}
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_state(self, state: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with (self.data_dir / STATE_FILE).open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
