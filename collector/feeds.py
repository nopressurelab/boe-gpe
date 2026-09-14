"""Atom 1.0 feed generation (one global, one per source, one per topic).

The feed titles and summaries below are part of what subscribers read, so they
stay in Spanish like the rest of the published site.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from .classify import Classifier
from .config import Config
from .util import now_utc, rfc3339, truncate

log = logging.getLogger(__name__)

FEED_DIR = "feeds"


def _tag_uri(base_url: str, item: dict[str, Any]) -> str:
    host = urlparse(base_url).netloc or "boletines-ambientales"
    return f"tag:{host},{item.get('date', '1970-01-01')}:{item.get('id', '')}"


def _entry(item: dict[str, Any], base_url: str, classifier: Classifier) -> str:
    title = escape(item.get("title", ""))
    link = escape(item.get("url", "") or base_url)
    updated = rfc3339(item.get("first_seen") or item.get("date"))
    published = rfc3339(item.get("date"))
    bits = []
    for key, label in (("source_name", "Fuente"), ("department", "Organismo"),
                       ("section", "Sección")):
        value = item.get(key)
        if value:
            bits.append(f"{label}: {escape(str(value))}")
    topics = ", ".join(classifier.topic_label(t) for t in item.get("topics", []))
    if topics:
        bits.append(f"Temas: {escape(topics)}")
    if item.get("summary"):
        bits.append(escape(truncate(item["summary"], 300)))
    summary = "<br/>".join(bits)
    categories = "".join(
        f'\n    <category term="{escape(t)}" label="{escape(classifier.topic_label(t))}"/>'
        for t in item.get("topics", []))
    pdf = ""
    if item.get("pdf_url") and item["pdf_url"] != item.get("url"):
        pdf = f'\n    <link rel="enclosure" type="application/pdf" href="{escape(item["pdf_url"])}"/>'
    return f"""  <entry>
    <id>{escape(_tag_uri(base_url, item))}</id>
    <title>{title}</title>
    <link rel="alternate" type="text/html" href="{link}"/>{pdf}
    <updated>{updated}</updated>
    <published>{published}</published>
    <author><name>{escape(item.get('source_name', ''))}</name></author>{categories}
    <summary type="html">{summary}</summary>
  </entry>"""


def render_feed(*, title: str, subtitle: str, feed_url: str, site_url: str,
                items: list[dict[str, Any]], base_url: str, classifier: Classifier,
                author: dict[str, str], rights: str = "") -> str:
    updated = rfc3339(now_utc())
    if items:
        newest = max((i.get("first_seen") or i.get("date", "") for i in items), default="")
        if newest:
            updated = rfc3339(newest)
    entries = "\n".join(_entry(item, base_url, classifier) for item in items)
    rights_tag = f"\n  <rights>{escape(rights)}</rights>" if rights else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="es">
  <id>{escape(feed_url)}</id>
  <title>{escape(title)}</title>
  <subtitle>{escape(subtitle)}</subtitle>
  <link rel="self" type="application/atom+xml" href="{escape(feed_url)}"/>
  <link rel="alternate" type="text/html" href="{escape(site_url)}"/>
  <updated>{updated}</updated>
  <author><name>{escape(author.get('name', ''))}</name><uri>{escape(author.get('uri', ''))}</uri></author>
  <generator uri="https://github.com/">boletines-ambientales</generator>{rights_tag}
{entries}
</feed>
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_all(cfg: Config, items: list[dict[str, Any]], classifier: Classifier,
              output_dir: Path) -> list[dict[str, str]]:
    """Write the configured feeds and return their catalogue for the site."""
    site = cfg.site
    base_url = cfg.base_url
    feeds_cfg = cfg.site_doc.get("feeds", {})
    max_items = int(cfg.build.get("feed_max_items", 150))
    author = site.get("author", {})
    rights = site.get("license", "")
    catalogue: list[dict[str, str]] = []

    def emit(slug: str, title: str, subtitle: str, selector: Callable[[dict], bool],
             page: str) -> None:
        selected = [i for i in items if selector(i)][:max_items]
        rel_path = f"{FEED_DIR}/{slug}.xml"
        feed_url = f"{base_url}/{rel_path}"
        xml = render_feed(title=title, subtitle=subtitle, feed_url=feed_url,
                          site_url=f"{base_url}/{page}", items=selected,
                          base_url=base_url, classifier=classifier, author=author,
                          rights=rights)
        _write(output_dir / rel_path, xml)
        catalogue.append({"slug": slug, "title": title, "subtitle": subtitle,
                          "url": feed_url, "path": rel_path,
                          "count": str(len(selected))})

    site_title = site.get("title", "Boletines")
    if feeds_cfg.get("all", True):
        emit("todo", f"{site_title} · todas las fuentes",
             site.get("tagline", ""), lambda i: True, "")
    if feeds_cfg.get("per_source", True):
        for source in cfg.sources:
            sid = source["id"]
            emit(f"fuente-{sid}", f"{site_title} · {source.get('name', sid)}",
                 f"Disposiciones ambientales publicadas en {source.get('name', sid)}",
                 lambda i, sid=sid: i.get("source") == sid, "fuentes.html")
    if feeds_cfg.get("per_topic", True):
        for topic in classifier.topic_meta():
            tid = topic["id"]
            emit(f"tema-{tid}", f"{site_title} · {topic['label']}",
                 f"Disposiciones clasificadas como «{topic['label']}»",
                 lambda i, tid=tid: tid in (i.get("topics") or []), "temas.html")
    if feeds_cfg.get("per_doc_type", False):
        for doc in classifier.doc_type_meta():
            did = doc["id"]
            emit(f"tipo-{did}", f"{site_title} · {doc['label']}", doc["label"],
                 lambda i, did=did: did in (i.get("doc_types") or []), "temas.html")
    log.info("Generated %s feeds", len(catalogue))
    return catalogue
