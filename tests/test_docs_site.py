import json
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
SITE_URL = "https://kirvo-reporting.github.io/video-to-notes/"


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str | None]] = []
        self.references: list[str] = []
        self.json_ld_parts: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "meta":
            key = values.get("name") or values.get("property")
            content = values.get("content")
            if key and content:
                self.meta[key] = content
        elif tag == "link":
            self.links.append(values)
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._in_json_ld = True

        for attribute in ("href", "src", "poster"):
            reference = values.get(attribute)
            if reference:
                self.references.append(reference)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "script" and self._in_json_ld:
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_h1:
            self.h1_parts.append(data)
        if self._in_json_ld:
            self.json_ld_parts.append(data)


class DocsSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parser = _SiteParser()
        cls.parser.feed((DOCS_ROOT / "index.html").read_text(encoding="utf-8"))

    def test_search_metadata_is_present(self) -> None:
        title = "".join(self.parser.title_parts).strip()
        description = self.parser.meta.get("description", "")
        canonical = next(
            (
                link.get("href")
                for link in self.parser.links
                if link.get("rel") == "canonical"
            ),
            None,
        )

        self.assertIn("Video to Notes", title)
        self.assertIn("YouTube", title)
        self.assertGreaterEqual(len(description), 80)
        self.assertLessEqual(len(description), 180)
        self.assertEqual(canonical, SITE_URL)
        self.assertEqual(self.parser.meta.get("og:url"), SITE_URL)
        self.assertEqual(self.parser.meta.get("twitter:card"), "summary_large_image")

    def test_page_has_one_clear_h1(self) -> None:
        h1 = " ".join("".join(self.parser.h1_parts).split())
        self.assertEqual(h1, "Turn videos into timestamped notes—locally.")

    def test_structured_data_matches_repository(self) -> None:
        payload = json.loads("".join(self.parser.json_ld_parts))
        self.assertEqual(payload["@type"], "SoftwareSourceCode")
        self.assertEqual(payload["name"], "video-to-notes")
        self.assertEqual(
            payload["codeRepository"],
            "https://github.com/KIRVO-REPORTING/video-to-notes",
        )
        self.assertEqual(payload["version"], "0.2.0")

    def test_local_page_references_exist(self) -> None:
        missing: list[str] = []
        for reference in self.parser.references:
            parsed = urlparse(reference)
            if parsed.scheme or parsed.netloc or reference.startswith("#"):
                continue
            path = parsed.path.lstrip("/")
            if path and not (DOCS_ROOT / path).exists():
                missing.append(reference)
        self.assertEqual(missing, [])

    def test_sitemap_points_to_canonical_page(self) -> None:
        sitemap = ET.parse(DOCS_ROOT / "sitemap.xml")
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [
            element.text
            for element in sitemap.findall("sitemap:url/sitemap:loc", namespace)
        ]
        self.assertEqual(locations, [SITE_URL])


if __name__ == "__main__":
    unittest.main()
