"""Text, date and identifier helpers. No external dependencies."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import re
import unicodedata
from email.utils import parsedate_to_datetime

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def strip_html(text: str) -> str:
    """Turn an HTML fragment into readable plain text."""
    if not text:
        return ""
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", " ", text)
    text = re.sub(r"(?i)</\s*(p|div|li|tr)\s*>", " ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize(text: str, *, lowercase: bool = True, accents: bool = True,
              collapse_whitespace: bool = True) -> str:
    """Normalize text so terms can be compared regardless of case and accents."""
    if not text:
        return ""
    if lowercase:
        text = text.lower()
    if accents:
        text = strip_accents(text)
    if collapse_whitespace:
        text = _WS_RE.sub(" ", text).strip()
    return text


def slugify(text: str) -> str:
    return _SLUG_RE.sub("-", normalize(text)).strip("-") or "x"


def digest(*parts: str) -> str:
    h = hashlib.sha1()
    for part in parts:
        h.update((part or "").encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:16]


_DATE_PATTERNS = (
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}")),
    ("%Y%m%d", re.compile(r"^\d{8}$")),
    ("%d/%m/%Y", re.compile(r"^\d{2}/\d{2}/\d{4}")),
    ("%d-%m-%Y", re.compile(r"^\d{2}-\d{2}-\d{4}")),
)


def parse_date(value: str | None) -> dt.date | None:
    """Accept RFC-822, ISO-8601 and the formats the gazettes actually use."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    for fmt, pattern in _DATE_PATTERNS:
        match = pattern.match(raw)
        if match:
            try:
                return dt.datetime.strptime(match.group(0), fmt).date()
            except ValueError:
                pass
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def daterange(end: dt.date, days: int) -> list[dt.date]:
    """The `days` days ending at `end`, oldest first."""
    days = max(1, int(days))
    return [end - dt.timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def rfc3339(moment: dt.datetime | dt.date | str | None) -> str:
    """Accept a datetime, a date or a string (ISO or gazette) and return UTC RFC-3339."""
    if moment is None or moment == "":
        moment = now_utc()
    if isinstance(moment, str):
        try:
            moment = dt.datetime.fromisoformat(moment.replace("Z", "+00:00"))
        except ValueError:
            moment = parse_date(moment) or now_utc()
    if isinstance(moment, dt.datetime):
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=dt.timezone.utc)
        return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return dt.datetime(moment.year, moment.month, moment.day,
                       tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_date_es(value: str) -> str:
    """Format a date for the published site, which is in Spanish.

    '2026-09-14' -> '14 de septiembre de 2026'.
    """
    months = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    parsed = parse_date(value)
    if not parsed:
        return value or ""
    return f"{parsed.day} de {months[parsed.month - 1]} de {parsed.year}"


def truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"
