"""Minimal HTTP client with retries, standard library only."""

from __future__ import annotations

import gzip
import logging
import time
import urllib.error
import urllib.request
import zlib

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, user_agent: str, timeout: int = 45, retries: int = 3,
                 backoff: float = 4.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = max(1, int(retries))
        self.backoff = backoff

    def get_bytes(self, url: str, accept: str | None = None) -> tuple[bytes, str | None]:
        """Return (body, charset declared by the server)."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "es,gl;q=0.8,ca;q=0.8,eu;q=0.8",
        }
        if accept:
            headers["Accept"] = accept
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    encoding = (response.headers.get("Content-Encoding") or "").lower()
                    if encoding == "gzip":
                        raw = gzip.decompress(raw)
                    elif encoding == "deflate":
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    return raw, response.headers.get_content_charset()
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (404, 410):
                    raise FetchError(f"{exc.code} for {url}") from exc
            except Exception as exc:  # noqa: BLE001 - flaky network, retry
                last_error = exc
            if attempt < self.retries:
                wait = self.backoff * attempt
                log.warning("Retry %s/%s in %.0fs for %s (%s)",
                            attempt, self.retries, wait, url, last_error)
                time.sleep(wait)
        raise FetchError(f"Could not download {url}: {last_error}")

    def get_text(self, url: str, accept: str | None = None,
                 encoding: str | None = None) -> str:
        raw, server_charset = self.get_bytes(url, accept=accept)
        for candidate in (encoding, server_charset, "utf-8", "iso-8859-1"):
            if not candidate:
                continue
            try:
                return raw.decode(candidate)
            except (LookupError, UnicodeDecodeError):
                continue
        return raw.decode("utf-8", errors="replace")

    def get_json(self, url: str, accept: str = "application/json") -> dict:
        import json

        return json.loads(self.get_text(url, accept=accept))
