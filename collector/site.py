"""Static site generation for GitHub Pages.

The page bodies below are written in Spanish on purpose: they are the published
site, read by people following Spanish official gazettes.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from html import escape
from pathlib import Path
from typing import Any

from .classify import Classifier
from .config import Config
from .store import Store
from .util import format_date_es, now_utc, rfc3339

log = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


def render(template: str, context: dict[str, Any]) -> str:
    return _PLACEHOLDER.sub(lambda m: str(context.get(m.group(1), "")), template)


class SiteBuilder:
    def __init__(self, cfg: Config, classifier: Classifier, templates_dir: Path):
        self.cfg = cfg
        self.classifier = classifier
        self.templates_dir = templates_dir
        self.ui = cfg.ui
        self.labels = self.ui.get("labels", {})
        self.nav_labels = self.ui.get("nav", {})
        self._cache: dict[str, str] = {}

    def template(self, name: str) -> str:
        if name not in self._cache:
            self._cache[name] = (self.templates_dir / name).read_text(encoding="utf-8")
        return self._cache[name]

    # -- shared structure ---------------------------------------------------
    def _nav(self, current: str) -> str:
        pages = [
            ("index.html", self.nav_labels.get("home", "Inicio")),
            ("fuentes.html", self.nav_labels.get("sources", "Fuentes")),
            ("temas.html", self.nav_labels.get("topics", "Temas")),
            ("suscripcion.html", self.nav_labels.get("feeds", "Suscripción")),
            ("metodologia.html", self.nav_labels.get("about", "Metodología")),
        ]
        parts = []
        for href, text in pages:
            current_attr = ' aria-current="page"' if href == current else ""
            parts.append(f'<a href="{href}"{current_attr}>{escape(text)}</a>')
        return "".join(parts)

    def _shell(self, *, page: str, title: str, description: str, content: str,
               state: dict[str, Any]) -> str:
        site = self.cfg.site
        last_run = state.get("last_run", "")
        last_run_line = (f"{self.labels.get('last_run', 'Última recogida')}: "
                         f"{escape(last_run)}") if last_run else ""
        return render(self.template("base.html"), {
            "lang": site.get("language", "es"),
            "page_title": escape(title),
            "page_description": escape(description),
            "site_title": escape(site.get("title", "")),
            "nav": self._nav(page),
            "content": content,
            "footer_note": escape(self.ui.get("footer_note", "")),
            "last_run_line": last_run_line,
            "repository_url": escape(site.get("repository_url", "")),
            "license": escape(site.get("license", "")),
            "license_url": escape(site.get("license_url", "")),
            "root": "",
        })

    # -- pages --------------------------------------------------------------
    def _item_html(self, item: dict[str, Any]) -> str:
        topics = item.get("topics") or []
        tags = "".join(
            f'<li>{escape(self.classifier.topic_label(t))}</li>' for t in topics)
        for doc_type in item.get("doc_types") or []:
            for meta in self.classifier.doc_type_meta():
                if meta["id"] == doc_type:
                    tags += f'<li>{escape(meta["label"])}</li>'
        org_bits = [b for b in (item.get("department"), item.get("section"),
                                item.get("subsection")) if b]
        links = [f'<a href="{escape(item["url"])}" rel="noopener">'
                 f'{escape(self.labels.get("original", "Texto oficial"))}</a>'] if item.get("url") else []
        if item.get("pdf_url") and item["pdf_url"] != item.get("url"):
            links.append(f'<a href="{escape(item["pdf_url"])}" rel="noopener">'
                         f'{escape(self.labels.get("pdf", "PDF"))}</a>')
        return render(self.template("item.html"), {
            "source": escape(item.get("source", "")),
            "source_name": escape(item.get("source_name", "")),
            "source_short": escape(item.get("source_short", "")),
            "topic_ids": escape(" ".join(topics)),
            "date": escape(item.get("date", "")),
            "date_label": escape(format_date_es(item.get("date", ""))),
            "region": escape(item.get("region", "")),
            "score": escape(f'{float(item.get("score", 0)):.1f}'),
            "title": escape(item.get("title", "")),
            "url": escape(item.get("url", "")),
            "org_line": escape(" · ".join(org_bits)),
            "tags": tags,
            "links": " ".join(links),
        })

    def index(self, items: list[dict[str, Any]], state: dict[str, Any],
              archive_count: int | None = None) -> str:
        site = self.cfg.site
        source_options = "".join(
            f'<option value="{escape(s["id"])}">{escape(s.get("short_name", s["id"]))}</option>'
            for s in self.cfg.sources)
        present = {t for item in items for t in (item.get("topics") or [])}
        topic_options = "".join(
            f'<option value="{escape(t["id"])}">{escape(t["label"])}</option>'
            for t in self.classifier.topic_meta() if t["id"] in present)
        content = render(self.template("index.html"), {
            "site_title": escape(site.get("title", "")),
            "tagline": escape(site.get("tagline", "")),
            "item_count": archive_count if archive_count is not None else len(items),
            "shown_count": len(items),
            "items_found": escape(self.labels.get("items_found", "disposiciones")),
            "recent_days": int(self.cfg.build.get("recent_days", 60)),
            "source_count": len(self.cfg.sources),
            "search_placeholder": escape(self.labels.get("search_placeholder", "Buscar")),
            "label_source": escape(self.labels.get("source", "Fuente")),
            "label_topics": escape(self.labels.get("topics", "Temas")),
            "all_sources": escape(self.labels.get("all_sources", "Todas")),
            "all_topics": escape(self.labels.get("all_topics", "Todos")),
            "source_options": source_options,
            "topic_options": topic_options,
            "items": "\n".join(self._item_html(i) for i in items),
            "no_results": escape(self.labels.get("no_results", "Sin resultados")),
            "root": "",
        })
        return self._shell(page="index.html", title=site.get("title", ""),
                           description=site.get("description", ""), content=content,
                           state=state)

    def _page(self, *, page: str, heading: str, lede: str, body: str,
              state: dict[str, Any]) -> str:
        content = render(self.template("page.html"), {
            "heading": escape(heading), "lede": escape(lede), "body": body})
        return self._shell(page=page, title=f"{heading} · {self.cfg.site.get('title', '')}",
                           description=lede, content=content, state=state)

    def sources_page(self, items: list[dict[str, Any]], state: dict[str, Any]) -> str:
        counts: dict[str, int] = {}
        for item in items:
            counts[item.get("source", "")] = counts.get(item.get("source", ""), 0) + 1
        rows = []
        for source in self.cfg.sources:
            sid = source["id"]
            stats = (state.get("sources") or {}).get(sid, {})
            rows.append(
                f"<tr><td><strong>{escape(source.get('short_name', sid))}</strong><br>"
                f"<span class='muted'>{escape(source.get('name', ''))}</span></td>"
                f"<td>{escape(source.get('region', ''))}</td>"
                f"<td>{escape(source.get('adapter', ''))}</td>"
                f"<td>{counts.get(sid, 0)}</td>"
                f"<td>{stats.get('seen', 0)}</td>"
                f"<td><a href='{escape(source.get('homepage', ''))}'>web</a> · "
                f"<a href='feeds/fuente-{escape(sid)}.xml'>Atom</a></td></tr>")
        pending = "".join(
            f"<tr class='pending'><td><strong>{escape(s.get('short_name', s['id']))}</strong><br>"
            f"<span class='muted'>{escape(s.get('name', ''))}</span></td>"
            f"<td>{escape(s.get('region', ''))}</td>"
            f"<td colspan='4'>{escape(s.get('notes', 'Pendiente'))}</td></tr>"
            for s in self.cfg.sources_doc.get("pending_sources", []))
        body = f"""
<table>
<thead><tr><th>Boletín</th><th>Ámbito</th><th>Adaptador</th><th>Publicadas</th><th>Revisadas</th><th>Enlaces</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<h2>Boletines pendientes de integrar</h2>
<p>Cada uno necesita localizar un feed o un servicio de datos abiertos utilizable. Al resolverlo basta con mover su entrada de <code>pending_sources</code> a <code>sources</code> en <code>config/sources.json</code> y marcar <code>"enabled": true</code>.</p>
<table>
<thead><tr><th>Boletín</th><th>Ámbito</th><th>Situación</th></tr></thead>
<tbody>{pending}</tbody>
</table>
"""
        return self._page(page="fuentes.html", heading="Fuentes",
                          lede="Boletines oficiales consultados cada día y su estado de integración.",
                          body=body, state=state)

    def topics_page(self, items: list[dict[str, Any]], state: dict[str, Any]) -> str:
        counts: dict[str, int] = {}
        for item in items:
            for topic in item.get("topics") or []:
                counts[topic] = counts.get(topic, 0) + 1
        rows = "".join(
            f"<tr><td><strong>{escape(t['label'])}</strong></td>"
            f"<td><code>{escape(t['id'])}</code></td><td>{counts.get(t['id'], 0)}</td>"
            f"<td><a href='index.html?tema={escape(t['id'])}'>ver</a> · "
            f"<a href='feeds/tema-{escape(t['id'])}.xml'>Atom</a></td></tr>"
            for t in self.classifier.topic_meta())
        doc_rows = "".join(
            f"<tr><td>{escape(d['label'])}</td><td><code>{escape(d['id'])}</code></td></tr>"
            for d in self.classifier.doc_type_meta())
        body = f"""
<table>
<thead><tr><th>Tema</th><th>Identificador</th><th>Disposiciones</th><th>Enlaces</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<h2>Tipos de documento</h2>
<p>Etiquetas transversales que se añaden a cada disposición ya clasificada como ambiental.</p>
<table><thead><tr><th>Tipo</th><th>Identificador</th></tr></thead><tbody>{doc_rows}</tbody></table>
"""
        return self._page(page="temas.html", heading="Temas",
                          lede="Clasificación temática definida en config/classification.json.",
                          body=body, state=state)

    def feeds_page(self, catalogue: list[dict[str, str]], state: dict[str, Any]) -> str:
        entries = "".join(
            f"<li><a href='{escape(feed['path'])}'>{escape(feed['title'])}</a>"
            f"<span class='url'>{escape(feed['url'])}</span></li>"
            for feed in catalogue)
        body = f"""
<p>Todos los canales son <strong>Atom 1.0</strong> y funcionan en cualquier lector (NetNewsWire, Feedly, Thunderbird, Miniflux, FreshRSS…). Copie la dirección del canal que le interese y péguela en su lector.</p>
<ul class="feed-list">{entries}</ul>
<h2>Datos en bruto</h2>
<p>Las mismas disposiciones están disponibles como JSON en <a href="api/items.json"><code>api/items.json</code></a> y el catálogo de fuentes y temas en <a href="api/meta.json"><code>api/meta.json</code></a>.</p>
"""
        return self._page(page="suscripcion.html", heading="Suscripción",
                          lede="Un canal Atom global, uno por boletín y uno por tema.",
                          body=body, state=state)

    def about_page(self, state: dict[str, Any]) -> str:
        scoring = self.cfg.classification.get("scoring", {})
        weights = "".join(
            f"<tr><td><code>{escape(field)}</code></td><td>{value}</td></tr>"
            for field, value in (scoring.get("field_weights") or {}).items())
        totals = state.get("totals", {})
        body = f"""
<p>Cada día una acción de GitHub descarga el sumario de los boletines configurados, puntúa cada disposición con un diccionario de términos ambientales y publica las que superan el umbral. No hay intervención manual ni modelos de lenguaje: la regla que decide es legible y auditable.</p>

<h2>Cómo se puntúa</h2>
<p>Cada término del diccionario tiene un peso. Si aparece en un campo de la disposición, suma <em>peso del término × peso del campo</em>. Se publica cuando la suma alcanza <code>{scoring.get('min_score', 3)}</code>.</p>
<table><thead><tr><th>Campo</th><th>Peso</th></tr></thead><tbody>{weights}</tbody></table>
<p>Un tema se asigna a la disposición cuando sus propios términos suman al menos <code>{scoring.get('min_topic_score', 1.5)}</code>. Los organismos con competencia ambiental suman puntos adicionales, y una lista de exclusiones resta puntos a los anuncios de personal, oposiciones y convenios colectivos, que de otro modo entrarían por el nombre de la consejería.</p>

<h2>Última ejecución</h2>
<p>{escape(str(state.get('last_run', 'sin datos')))} · {totals.get('seen', 0)} disposiciones revisadas, {totals.get('relevant', 0)} publicadas.</p>

<h2>Ajustar los criterios</h2>
<p>Todo el comportamiento vive en tres ficheros JSON del repositorio: <code>config/sources.json</code> (qué boletines se leen y cómo), <code>config/classification.json</code> (el vocabulario y los umbrales) y <code>config/site.json</code> (el sitio y los feeds). El código no contiene ninguna URL ni ninguna palabra clave.</p>

<h2>Advertencia</h2>
<p>{escape(self.ui.get('footer_note', ''))}</p>
"""
        return self._page(page="metodologia.html", heading="Metodología",
                          lede="Cómo se seleccionan y clasifican las disposiciones.",
                          body=body, state=state)


def build(cfg: Config, classifier: Classifier, *, templates_dir: Path,
          catalogue_builder) -> dict[str, Any]:
    store = Store(cfg.data_dir)
    recent_days = int(cfg.build.get("recent_days", 60))
    max_items = int(cfg.build.get("max_items_on_index", 300))
    items = store.recent_items(recent_days)
    state = store.load_state()
    output = cfg.output_dir
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    catalogue = catalogue_builder(items, output)
    builder = SiteBuilder(cfg, classifier, templates_dir)
    page_items = items[:max_items]

    (output / "index.html").write_text(
        builder.index(page_items, state, archive_count=len(items)), encoding="utf-8")
    (output / "fuentes.html").write_text(builder.sources_page(items, state), encoding="utf-8")
    (output / "temas.html").write_text(builder.topics_page(items, state), encoding="utf-8")
    (output / "suscripcion.html").write_text(builder.feeds_page(catalogue, state), encoding="utf-8")
    (output / "metodologia.html").write_text(builder.about_page(state), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")

    assets_src = templates_dir / "assets"
    if assets_src.is_dir():
        shutil.copytree(assets_src, output / "assets", dirs_exist_ok=True)

    api_dir = output / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    (api_dir / "items.json").write_text(json.dumps(
        {"generated_at": rfc3339(now_utc()), "count": len(items), "items": items},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (api_dir / "meta.json").write_text(json.dumps({
        "generated_at": rfc3339(now_utc()),
        "site": cfg.site,
        "sources": [{k: s.get(k) for k in
                     ("id", "name", "short_name", "region", "scope", "homepage", "adapter")}
                    for s in cfg.sources],
        "topics": classifier.topic_meta(),
        "doc_types": classifier.doc_type_meta(),
        "feeds": catalogue,
        "state": state,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    log.info("Site generated in %s with %s provisions", output, len(items))
    return {"items": len(items), "pages": 5, "feeds": len(catalogue)}
