"""Adapter for the BOE open-data summary API."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from ..http import FetchError
from .base import Adapter, RawItem

log = logging.getLogger(__name__)


class BoeSumarioAdapter(Adapter):
    """Walks section -> department -> epigraph -> provision.

    The API alternates between object and list at nearly every level, hence
    `as_list`.
    """

    name = "boe_sumario"

    def collect(self, dates: list[dt.date]) -> list[RawItem]:
        template = self.options.get("url_template")
        if not template:
            log.warning("[%s] missing 'url_template' in options", self.source_id)
            return []
        accept = self.options.get("accept", "application/json")
        url_field = self.options.get("url_field", "url_html")
        pdf_field = self.options.get("pdf_field", "url_pdf")
        skip_sections = {str(code) for code in self.options.get("skip_section_codes", [])}

        items: list[RawItem] = []
        for day in dates:
            url = self.render_template(template, day)
            try:
                payload = self.client.get_json(url, accept=accept)
            except FetchError as exc:
                log.info("[%s] no summary for %s (%s)", self.source_id, day, exc)
                continue
            status = (payload.get("status") or {}).get("code")
            if status and str(status) != "200":
                log.info("[%s] %s returned status %s", self.source_id, day, status)
                continue
            items.extend(self._parse(payload, day, url_field, pdf_field, skip_sections))
        return items

    def _parse(self, payload: dict[str, Any], day: dt.date, url_field: str,
               pdf_field: str, skip_sections: set[str]) -> list[RawItem]:
        sumario = ((payload.get("data") or {}).get("sumario") or {})
        published = self._published_date(sumario, day)
        found: list[RawItem] = []
        for diario in self.as_list(sumario.get("diario")):
            for seccion in self.as_list(diario.get("seccion")):
                if str(seccion.get("codigo", "")) in skip_sections:
                    continue
                section_name = seccion.get("nombre", "")
                for departamento in self.as_list(seccion.get("departamento")):
                    department_name = departamento.get("nombre", "")
                    blocks = [("", departamento)]
                    blocks += [(e.get("nombre", ""), e)
                               for e in self.as_list(departamento.get("epigrafe"))]
                    for epigraph_name, block in blocks:
                        for entry in self.as_list(block.get("item")):
                            raw = self._item(entry, published, section_name,
                                             epigraph_name, department_name,
                                             url_field, pdf_field)
                            if raw:
                                found.append(raw)
        return found

    def _published_date(self, sumario: dict[str, Any], fallback: dt.date) -> dt.date:
        from ..util import parse_date

        meta = sumario.get("metadatos") or {}
        return parse_date(meta.get("fecha_publicacion")) or fallback

    def _item(self, entry: dict[str, Any], published: dt.date, section: str,
              epigraph: str, department: str, url_field: str,
              pdf_field: str) -> RawItem | None:
        title = (entry.get("titulo") or "").strip()
        if not title:
            return None
        url = self._url(entry.get(url_field)) or self._url(entry.get(pdf_field))
        return RawItem(
            title=title,
            url=url,
            pdf_url=self._url(entry.get(pdf_field)),
            date=published,
            section=section,
            subsection=epigraph,
            department=department,
            summary="",
            identifier=entry.get("identificador", ""),
            extra={"control": entry.get("control", "")},
        )

    @staticmethod
    def _url(value: Any) -> str:
        """url_pdf arrives as an object {szBytes, texto}; url_html as a string."""
        if isinstance(value, dict):
            return (value.get("texto") or "").strip()
        return (value or "").strip() if isinstance(value, str) else ""
