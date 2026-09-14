"""Generic adapter for RSS 2.0 and Atom channels.

Everything specific to a given gazette (URLs, encoding, which field the section
or the issuing body comes from) is declared in `options`, never in the code.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import xml.etree.ElementTree as ET

from ..http import FetchError
from ..util import parse_date, strip_html
from .base import Adapter, RawItem

log = logging.getLogger(__name__)

_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find(element: ET.Element, *names: str) -> ET.Element | None:
    wanted = {n.lower() for n in names}
    for child in element:
        if _local(child.tag) in wanted:
            return child
    return None


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


class RssAdapter(Adapter):
    name = "rss"

    def collect(self, dates: list[dt.date]) -> list[RawItem]:
        urls = self.options.get("urls") or []
        if not urls:
            log.warning("[%s] no URLs configured", self.source_id)
            return []
        wanted = set(dates)
        skip_patterns = [re.compile(p, re.IGNORECASE)
                         for p in self.options.get("skip_title_patterns", [])]
        collected: list[RawItem] = []
        for url in urls:
            try:
                root = self._parse_feed(url)
            except (FetchError, ET.ParseError) as exc:
                log.warning("[%s] could not read %s: %s", self.source_id, url, exc)
                continue
            collected.extend(self._items(root, wanted, skip_patterns))
        return collected

    # -- download and parse ---------------------------------------------
    def _parse_feed(self, url: str) -> ET.Element:
        raw, server_charset = self.client.get_bytes(url, accept="application/rss+xml, application/xml, text/xml, */*")
        forced = self.options.get("encoding")
        if forced:
            text = raw.decode(forced, errors="replace")
            return ET.fromstring(_DECL_RE.sub("", text).strip())
        try:
            return ET.fromstring(raw)
        except ET.ParseError:
            text = raw.decode(server_charset or "utf-8", errors="replace")
            return ET.fromstring(_DECL_RE.sub("", text).strip())

    def _items(self, root: ET.Element, wanted: set[dt.date],
               skip_patterns: list[re.Pattern[str]]) -> list[RawItem]:
        channel = _find(root, "channel") or root
        channel_title = _text(_find(channel, "title"))
        channel_date = parse_date(_text(_find(channel, "pubdate"))
                                  or _text(_find(channel, "lastbuilddate"))
                                  or _text(_find(channel, "updated")))
        use_channel_date = bool(self.options.get("use_channel_date_as_fallback", True))
        strip = bool(self.options.get("strip_html", True))
        patterns = self._field_patterns()

        entries = [node for node in channel.iter() if _local(node.tag) in ("item", "entry")]
        found: list[RawItem] = []
        for entry in entries:
            title_raw = _text(_find(entry, "title"))
            if not title_raw or any(p.search(title_raw) for p in skip_patterns):
                continue
            published = parse_date(_text(_find(entry, "pubdate", "published",
                                               "updated", "date")))
            if published is None and use_channel_date:
                published = channel_date
            if wanted and published is not None and published not in wanted:
                continue

            summary_raw = _text(_find(entry, "description", "summary", "content"))
            category = _text(_find(entry, "category"))
            haystack = {
                "title": title_raw,
                "summary_raw": summary_raw,
                "summary": strip_html(summary_raw),
                "category": category,
                "channel_title": channel_title,
            }
            fields = {"section": "", "subsection": "", "department": ""}
            for source_field, pattern in patterns:
                match = pattern.search(haystack.get(source_field, ""))
                if not match:
                    continue
                for name, value in (match.groupdict() or {}).items():
                    if name in fields and not fields[name] and value:
                        fields[name] = strip_html(value) if strip else value.strip()
            if self.options.get("section_from_category") and category:
                fields["section"] = category
            if self.options.get("section_from_channel_title") and not fields["section"]:
                fields["section"] = channel_title

            found.append(RawItem(
                title=strip_html(title_raw) if strip else title_raw,
                url=self._link(entry),
                date=published,
                section=fields["section"],
                subsection=fields["subsection"],
                department=fields["department"],
                summary=strip_html(summary_raw) if strip else summary_raw,
                identifier=_text(_find(entry, "guid", "id")),
            ))
        return found

    def _field_patterns(self) -> list[tuple[str, re.Pattern[str]]]:
        """`field_patterns` in sources.json: regular expressions with named groups
        (section, subsection, department) applied to one field of the channel."""
        compiled: list[tuple[str, re.Pattern[str]]] = []
        for rule in self.options.get("field_patterns", []) or []:
            source_field = rule.get("from", "summary")
            pattern = rule.get("pattern")
            if not pattern:
                continue
            flags = 0
            for flag in (rule.get("flags") or ""):
                flags |= {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE}.get(flag, 0)
            try:
                compiled.append((source_field, re.compile(pattern, flags)))
            except re.error as exc:
                log.warning("[%s] invalid pattern %r: %s", self.source_id, pattern, exc)
        return compiled

    @staticmethod
    def _link(entry: ET.Element) -> str:
        node = _find(entry, "link")
        if node is None:
            return _text(_find(entry, "guid", "id"))
        return (node.get("href") or _text(node) or "").strip()
