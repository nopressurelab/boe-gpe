"""Common contract for gazette adapters."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

from ..http import HttpClient

log = logging.getLogger(__name__)


@dataclass
class RawItem:
    """A provision exactly as the gazette publishes it, before classification."""

    title: str
    url: str
    date: dt.date | None = None
    pdf_url: str = ""
    section: str = ""
    subsection: str = ""
    department: str = ""
    summary: str = ""
    identifier: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class Adapter:
    """Base class for every adapter.

    An adapter receives its source configuration (`options` in sources.json) and
    returns the provisions published on the requested dates.
    """

    name = "base"

    def __init__(self, source: dict[str, Any], client: HttpClient):
        self.source = source
        self.options = source.get("options", {}) or {}
        self.client = client

    @property
    def source_id(self) -> str:
        return self.source.get("id", "?")

    def collect(self, dates: list[dt.date]) -> list[RawItem]:  # pragma: no cover
        raise NotImplementedError

    # -- shared helpers --------------------------------------------------
    @staticmethod
    def as_list(value: Any) -> list[Any]:
        """Gazettes alternate between a single object and a list for one field."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def render_template(template: str, day: dt.date) -> str:
        return (template
                .replace("{yyyymmdd}", day.strftime("%Y%m%d"))
                .replace("{yyyy-mm-dd}", day.strftime("%Y-%m-%d"))
                .replace("{yyyy}", day.strftime("%Y"))
                .replace("{mm}", day.strftime("%m"))
                .replace("{dd}", day.strftime("%d")))
