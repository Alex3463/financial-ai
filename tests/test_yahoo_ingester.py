from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ingest.yahoo import _normalize_news_item  # noqa: E402


class YahooIngesterTests(unittest.TestCase):
    def test_normalize_news_item_supports_nested_content(self) -> None:
        raw_item = {
            "id": "123",
            "content": {
                "title": "Tech stocks today: AI chipmaker surges",
                "summary": "The artificial intelligence boom broadened.",
                "pubDate": "2026-05-11T10:00:00Z",
                "provider": {"displayName": "Yahoo Finance"},
                "canonicalUrl": {"url": "https://finance.yahoo.com/example"},
            },
        }

        normalized = _normalize_news_item(raw_item)

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["title"], raw_item["content"]["title"])
        self.assertEqual(normalized["publisher"], "Yahoo Finance")
        self.assertEqual(normalized["published"], "2026-05-11")
        self.assertEqual(normalized["link"], "https://finance.yahoo.com/example")
        self.assertIn("artificial intelligence", normalized["summary"])


if __name__ == "__main__":
    unittest.main()
