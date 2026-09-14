"""Orchestration of the daily run: sources -> classification -> store."""

from __future__ import annotations

import datetime as dt
import logging
from collections import defaultdict
from typing import Any

from . import adapters
from .classify import Classifier
from .config import Config
from .http import HttpClient
from .store import Store
from .util import daterange, digest, now_utc, rfc3339, truncate

log = logging.getLogger(__name__)

SUMMARY_LIMIT = 400


def build_client(cfg: Config) -> HttpClient:
    defaults = cfg.defaults
    return HttpClient(
        user_agent=defaults.get("user_agent", "boletines-ambientales/1.0"),
        timeout=int(defaults.get("timeout_seconds", 45)),
        retries=int(defaults.get("retries", 3)),
        backoff=float(defaults.get("retry_backoff_seconds", 4)),
    )


def _item_id(source_id: str, raw) -> str:
    return f"{source_id}-{digest(source_id, raw.identifier or raw.url or raw.title)}"


def collect(cfg: Config, *, days: int | None = None, end: dt.date | None = None,
            only: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    classifier = Classifier(cfg.classification)
    client = build_client(cfg)
    store = Store(cfg.data_dir)

    lookback = int(days if days is not None else cfg.defaults.get("lookback_days", 4))
    end_date = end or dt.date.today()
    dates = daterange(end_date, lookback)
    started = now_utc()

    per_source: dict[str, Any] = {}
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_seen = 0
    total_relevant = 0

    for source in cfg.sources:
        sid = source["id"]
        if only and sid not in only:
            continue
        try:
            adapter = adapters.get(source["adapter"])(source, client)
        except KeyError as exc:
            log.error("%s", exc)
            per_source[sid] = {"error": str(exc), "seen": 0, "relevant": 0}
            continue
        try:
            raw_items = adapter.collect(dates)
        except Exception as exc:  # noqa: BLE001 - one source being down must not stop the rest
            log.exception("[%s] collection failed", sid)
            per_source[sid] = {"error": str(exc), "seen": 0, "relevant": 0}
            continue

        relevant = 0
        for raw in raw_items:
            if raw.date is None:
                continue
            if raw.date not in dates:
                continue
            verdict = classifier.classify({
                "title": raw.title,
                "summary": raw.summary,
                "department": raw.department,
                "section": raw.section,
                "subsection": raw.subsection,
            })
            if not verdict.relevant:
                continue
            relevant += 1
            by_day[raw.date.isoformat()].append({
                "id": _item_id(sid, raw),
                "source": sid,
                "source_name": source.get("name", sid),
                "source_short": source.get("short_name", sid),
                "region": source.get("region", ""),
                "scope": source.get("scope", ""),
                "date": raw.date.isoformat(),
                "title": raw.title,
                "summary": truncate(raw.summary, SUMMARY_LIMIT),
                "section": raw.section,
                "subsection": raw.subsection,
                "department": raw.department,
                "url": raw.url,
                "pdf_url": raw.pdf_url,
                "identifier": raw.identifier,
                "score": verdict.score,
                "topics": verdict.topics,
                "doc_types": verdict.doc_types,
                "matches": verdict.matches[:12],
                "first_seen": rfc3339(started),
            })
        per_source[sid] = {"seen": len(raw_items), "relevant": relevant}
        total_seen += len(raw_items)
        total_relevant += relevant
        log.info("[%s] %s provisions, %s relevant", sid, len(raw_items), relevant)

    written: dict[str, dict[str, int]] = {}
    if not dry_run:
        for day, items in sorted(by_day.items()):
            new_count, total = store.merge_day(day, items)
            written[day] = {"nuevas": new_count, "total": total}
        retention = int(cfg.build.get("retention_days", 0))
        pruned = store.prune(retention) if retention else 0
        state = store.load_state()
        state.update({
            "last_run": rfc3339(started),
            "finished_at": rfc3339(now_utc()),
            "range": {"from": dates[0].isoformat(), "to": dates[-1].isoformat()},
            "sources": per_source,
            "totals": {"seen": total_seen, "relevant": total_relevant},
            "days_written": written,
            "days_pruned": pruned,
        })
        store.save_state(state)

    return {
        "range": [dates[0].isoformat(), dates[-1].isoformat()],
        "sources": per_source,
        "seen": total_seen,
        "relevant": total_relevant,
        "days": written,
    }
