"""Generic adapter for Opendatasoft portals (Explore API v2.1)."""

from __future__ import annotations

import datetime as dt
import logging
from urllib.parse import urlencode

from ..http import FetchError
from ..util import parse_date
from .base import Adapter, RawItem

log = logging.getLogger(__name__)


class OpenDataSoftAdapter(Adapter):
    name = "opendatasoft"

    def collect(self, dates: list[dt.date]) -> list[RawItem]:
        base = (self.options.get("base_url") or "").rstrip("/")
        dataset = self.options.get("dataset")
        date_field = self.options.get("date_field")
        field_map = self.options.get("field_map") or {}
        if not (base and dataset and date_field):
            log.warning("[%s] missing base_url, dataset or date_field", self.source_id)
            return []

        start, end = min(dates), max(dates)
        where = (f"{date_field} >= date'{start.isoformat()}' "
                 f"and {date_field} <= date'{end.isoformat()}'")
        page_size = int(self.options.get("page_size", 100))
        max_pages = int(self.options.get("max_pages", 20))

        found: list[RawItem] = []
        for page in range(max_pages):
            query = urlencode({
                "where": where,
                "limit": page_size,
                "offset": page * page_size,
                "order_by": f"{date_field} desc",
            })
            url = f"{base}/catalog/datasets/{dataset}/records?{query}"
            try:
                payload = self.client.get_json(url)
            except FetchError as exc:
                log.warning("[%s] error querying Opendatasoft: %s", self.source_id, exc)
                break
            results = payload.get("results") or []
            for record in results:
                item = self._to_item(record, field_map)
                if item:
                    found.append(item)
            if len(results) < page_size:
                break
        return found

    def _to_item(self, record: dict, field_map: dict) -> RawItem | None:
        def pick(key: str) -> str:
            source_key = field_map.get(key)
            if not source_key:
                return ""
            value = record.get(source_key)
            return str(value).strip() if value is not None else ""

        title = pick("title")
        if not title:
            return None
        return RawItem(
            title=title,
            url=pick("url") or pick("pdf_url"),
            pdf_url=pick("pdf_url"),
            date=parse_date(pick("date")),
            section=pick("section"),
            subsection=pick("subsection"),
            department=pick("department"),
            summary=pick("summary"),
            identifier=pick("identifier"),
        )
