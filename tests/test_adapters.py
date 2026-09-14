import datetime as dt
import unittest
from pathlib import Path

from collector.adapters.rss import RssAdapter
from collector.adapters.boe_sumario import BoeSumarioAdapter

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeClient:
    """Stand-in HTTP client: serves files from tests/fixtures."""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls = []

    def get_bytes(self, url, accept=None):
        self.calls.append(url)
        return self.payload, "utf-8"

    def get_json(self, url, accept="application/json"):
        import json
        self.calls.append(url)
        return json.loads(self.payload.decode("utf-8"))


class RssAdapterTest(unittest.TestCase):
    def build(self, **options):
        source = {"id": "test", "adapter": "rss", "options": options}
        client = FakeClient((FIXTURES / "sample.rss").read_bytes())
        return RssAdapter(source, client)

    def test_extracts_date_section_and_department(self):
        adapter = self.build(
            urls=["http://example.org/feed"],
            field_patterns=[{"from": "summary_raw",
                             "pattern": r"^\s*(?P<section>.*?)\s*</br>\s*(?P<department>.*?)\s*$",
                             "flags": "is"}],
        )
        items = adapter.collect([dt.date(2026, 9, 14)])
        self.assertEqual(len(items), 2)  # the one from the 13th is out of range
        first = items[0]
        self.assertEqual(first.date, dt.date(2026, 9, 14))
        self.assertEqual(first.section, "III. Otras disposiciones")
        self.assertEqual(first.department, "Consellería de Medio Ambiente")
        self.assertTrue(first.title.startswith("ANUNCIO por el que se somete"))
        self.assertEqual(first.url, "https://example.org/dispo/1.html")

    def test_skip_title_patterns(self):
        adapter = self.build(urls=["http://example.org/feed"],
                             skip_title_patterns=[r"^\s*Sumario\s*$"])
        items = adapter.collect([dt.date(2026, 9, 14)])
        self.assertEqual([i.title for i in items if i.title == "Sumario"], [])

    def test_date_range_covers_several_days(self):
        adapter = self.build(urls=["http://example.org/feed"])
        items = adapter.collect([dt.date(2026, 9, 13), dt.date(2026, 9, 14)])
        self.assertEqual(len(items), 3)

    def test_urls_come_from_config(self):
        adapter = self.build(urls=["http://example.org/otro"])
        adapter.collect([dt.date(2026, 9, 14)])
        self.assertEqual(adapter.client.calls, ["http://example.org/otro"])


class BoeAdapterTest(unittest.TestCase):
    PAYLOAD = (FIXTURES / "boe_sumario.json").read_bytes()

    def adapter(self, **options):
        options.setdefault("url_template", "https://boe.es/api/{yyyymmdd}")
        source = {"id": "boe", "adapter": "boe_sumario", "options": options}
        return BoeSumarioAdapter(source, FakeClient(self.PAYLOAD))

    def test_walks_objects_and_lists(self):
        items = self.adapter().collect([dt.date(2026, 9, 14)])
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].identifier, "BOE-A-1")
        self.assertEqual(items[0].section, "I. Disposiciones generales")
        self.assertEqual(items[0].subsection, "Aguas")
        self.assertEqual(items[0].department, "MINISTERIO X")
        self.assertEqual(items[0].url, "https://boe.es/a.html")
        self.assertEqual(items[0].pdf_url, "https://boe.es/a.pdf")

    def test_skipping_sections_is_configurable(self):
        items = self.adapter(skip_section_codes=["5"]).collect([dt.date(2026, 9, 14)])
        self.assertEqual([i.identifier for i in items], ["BOE-A-1"])

    def test_url_template(self):
        adapter = self.adapter(url_template="https://x/{yyyy}/{mm}/{dd}")
        adapter.collect([dt.date(2026, 9, 14)])
        self.assertEqual(adapter.client.calls, ["https://x/2026/09/14"])


if __name__ == "__main__":
    unittest.main()
