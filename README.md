# Boletines Ambientales

A static site, hosted on GitHub Pages, that collects environmentally relevant
provisions from the Spanish state gazette (**BOE**) and from regional official
gazettes once a day, classifies them with a transparent keyword ruleset, and
publishes **Atom feeds** so people can follow them in any feed reader.

Nothing is hard-coded: every URL, endpoint, keyword, weight and threshold lives
in three JSON files under [`config/`](config/). The Python code only applies
what the configuration says.

---

## How it works

```
config/sources.json ──▶ adapters (boe_sumario | rss | opendatasoft)
                             │
                             ▼
                     raw provisions for the last N days
                             │
config/classification.json ──▶ keyword scoring ──▶ relevant items
                             │
                             ▼
              data/items/YYYY-MM-DD.json  (committed to the repo)
                             │
config/site.json ────────────▶ public/  →  HTML pages + Atom feeds + JSON API
```

A scheduled GitHub Action runs daily at 06:30 UTC, commits the new data back to
the repository, rebuilds the site and deploys it to GitHub Pages. Because the
data lives in git, the archive grows over time and the feeds have real history.

## Sources

| Gazette | Region | Adapter | Access |
|---|---|---|---|
| BOE | Spain | `boe_sumario` | Official open-data JSON API |
| DOG | Galicia | `rss` | Full daily summary feed |
| BOC | Canarias | `rss` | One feed per chapter |
| DOE | Extremadura | `rss` | One feed per section (ISO-8859-1) |
| BOCYL | Castilla y León | `opendatasoft` | Open-data Explore API |

Thirteen further gazettes (BOJA, DOGC, BOPV, BOA, DOCM, DOGV, BON, BORM, BOCM,
BOIB, BOPA, BOC Cantabria, BOR) are listed under `pending_sources` in
`config/sources.json` with a note on what is missing for each. None of them
publishes an item-level feed at an address that could be verified, so they need
either a new adapter or a working endpoint. Moving one from `pending_sources`
to `sources` and setting `"enabled": true` is all that is needed once its feed
is known.

## Setup

1. Create a GitHub repository and push this directory to it.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write.**
   (The daily job commits the collected data back to the repository.)
4. Check `base_url`, `repository_url` and `author.uri` in `config/site.json`
   and the `user_agent` in `config/sources.json`. The workflow also passes the
   real Pages URL through `SITE_BASE_URL`, so feeds stay correct regardless.
5. Run the workflow once by hand: **Actions → Daily collection → Run workflow**.
   To seed an archive, set *How many days back to re-check* to e.g. `30` for
   the first run.

## Configuration

### `config/sources.json`

`defaults` sets the user agent, timeouts, retries and how many days back each
run re-checks (`lookback_days`; re-running a day is safe — items are merged by
id, never duplicated).

Each source declares an `adapter` and its `options`:

**`boe_sumario`** — the BOE open-data summary API.

```json
"options": {
  "url_template": "https://boe.es/datosabiertos/api/boe/sumario/{yyyymmdd}",
  "url_field": "url_html",
  "pdf_field": "url_pdf",
  "skip_section_codes": []
}
```

Placeholders available in any template: `{yyyymmdd}`, `{yyyy-mm-dd}`, `{yyyy}`,
`{mm}`, `{dd}`.

**`rss`** — any RSS 2.0 or Atom feed.

```json
"options": {
  "urls": ["https://example.org/feed.rss"],
  "encoding": "iso-8859-1",
  "use_channel_date_as_fallback": true,
  "skip_title_patterns": ["^\\s*Sumario\\s*$"],
  "section_from_category": true,
  "field_patterns": [
    { "from": "summary_raw",
      "pattern": "^(?P<section>.*?)</br>(?P<department>.*)$",
      "flags": "is" }
  ]
}
```

`field_patterns` is how the section, subsection and organism are pulled out of
whatever field a given gazette happens to use. Each rule is a regular
expression with named groups (`section`, `subsection`, `department`) applied to
one of `title`, `summary`, `summary_raw` (before HTML stripping), `category` or
`channel_title`. The first rule that fills a field wins.

**`opendatasoft`** — any Opendatasoft Explore v2.1 portal.

```json
"options": {
  "base_url": "https://jcyl.opendatasoft.com/api/explore/v2.1",
  "dataset": "bocyl",
  "date_field": "fecha_publicacion",
  "page_size": 100,
  "field_map": { "title": "titulo", "date": "fecha_publicacion", "url": "enlace_fichero_html" }
}
```

### `config/classification.json`

The whole vocabulary. A term scores *term weight × field weight* once per field
it appears in; an item is published when the total reaches `min_score`.

- `topics` — the taxonomy. Each topic's own terms decide whether that topic is
  attached to the item (`min_topic_score`).
- `boosts` — terms that add score without being a topic, used for the names of
  environmental departments and agencies.
- `exclusions` — negative weights that keep staffing notices, job boards and
  collective agreements out, which would otherwise enter through the name of
  the environment ministry.
- `doc_types` — cross-cutting labels (grants, public consultation, sanctions…)
  applied to items that are already relevant.

Matching is accent- and case-insensitive and respects word boundaries, so
`agua` does not match `aguardiente`. Raise `min_score` for a quieter feed,
lower it for wider coverage.

### `config/site.json`

Title, description, base URL, language, retention, how many days the front page
shows, which feeds to generate, and every user-visible string in the interface.

## Feeds

| Feed | Path |
|---|---|
| Everything | `feeds/todo.xml` |
| One per gazette | `feeds/fuente-<id>.xml` |
| One per topic | `feeds/tema-<id>.xml` |
| Raw JSON | `api/items.json`, `api/meta.json` |

All feeds are Atom 1.0 and work in NetNewsWire, Feedly, Thunderbird, Miniflux,
FreshRSS and anything else that speaks Atom.

## Local use

Python 3.11 or newer (CI runs 3.12) and no dependencies at all — everything is
standard library.

```bash
python -m collector check                      # validate config, no network
python -m collector collect --days 3           # fetch and classify
python -m collector collect --days 30 --source boe   # seed an archive
python -m collector collect --dry-run --verbose      # nothing is written
python -m collector build                      # site + feeds into public/
python -m collector run                        # both
python -m unittest discover -s tests           # tests
python -m http.server -d public 8000           # preview
```

## Data layout

```
data/items/YYYY-MM-DD.json   one file per publication date, items merged by id
data/state.json              last run, per-source counts, errors
```

Each item keeps the terms that matched and their contribution in `matches`, so
any decision the classifier made can be traced back.

## Limitations

- Relevance is decided by keywords, not by reading the text. Expect some false
  positives (a tender that merely mentions *residuos*) and some misses. The
  score shown next to every item and the `matches` field make tuning concrete.
- Regional coverage is partial; see the table above.
- Regional gazettes publish their feed for the current day only, so a gap in
  the daily run can lose a day for those sources. The BOE and Opendatasoft
  adapters can always be re-run for past dates.
- This is an unofficial index. The legally binding text is the one published in
  each official gazette.
