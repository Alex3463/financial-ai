from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from news.enrichment import (  # noqa: E402
    _enrich_news_async,
    _extract_json_block,
    build_fallback_summary,
    html_fragment_to_markdown,
    select_deep_read_candidates,
    summarize_article_markdown,
)


class FailingServer:
    async def __aenter__(self) -> "FailingServer":
        raise RuntimeError("MCP startup failed")

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class NewsEnrichmentTests(unittest.TestCase):
    def test_select_deep_read_candidates_prefers_company_specific_articles(self) -> None:
        articles = [
            {
                "title": "Apple earnings beat expectations on strong iPhone demand",
                "summary": "Revenue and guidance both moved higher.",
                "link": "https://example.com/earnings",
            },
            {
                "title": "General market wrap",
                "summary": "A quiet trading day.",
                "link": "https://example.com/market-wrap",
            },
            {
                "title": "Apple launches new on-device AI feature",
                "summary": "New on-device AI capabilities were previewed.",
                "link": "https://example.com/apple-ai-launch",
            },
        ]

        selected = select_deep_read_candidates(
            articles,
            ticker="AAPL",
            company_name="Apple Inc.",
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["link"], "https://example.com/earnings")
        self.assertIn("회사명/티커", selected[0]["selection_reason"])
        self.assertEqual(selected[1]["link"], "https://example.com/apple-ai-launch")
        self.assertIn("회사명/티커", selected[1]["selection_reason"])

    def test_select_deep_read_candidates_skips_sector_only_articles(self) -> None:
        articles = [
            {
                "title": "AI feature launch expands data center roadmap",
                "summary": "New on-device AI capabilities were previewed.",
                "link": "https://example.com/ai-launch",
            },
            {
                "title": "General market wrap",
                "summary": "A quiet trading day.",
                "link": "https://example.com/market-wrap",
            },
        ]

        selected = select_deep_read_candidates(
            articles,
            ticker="AAPL",
            company_name="Apple Inc.",
        )

        self.assertEqual(selected, [])

    def test_html_fragment_to_markdown_removes_non_content_tags(self) -> None:
        html = """
        <article>
          <style>.hidden { display:none; }</style>
          <script>console.log("ignored")</script>
          <noscript>ignored fallback</noscript>
          <h1>Headline</h1>
          <p>Key detail.</p>
        </article>
        """

        markdown = html_fragment_to_markdown(html)

        self.assertIn("# Headline", markdown)
        self.assertIn("Key detail.", markdown)
        self.assertNotIn("ignored", markdown)
        self.assertNotIn("console.log", markdown)

    def test_extract_json_block_parses_playwright_result(self) -> None:
        result_text = """
        ### Result
        {
          "pageTitle": "Example",
          "textLength": 512,
          "html": "<article><p>Hello</p></article>"
        }
        ### Ran Playwright code
        ```js
        await page.evaluate('...');
        ```
        """

        payload = _extract_json_block(result_text)

        self.assertEqual(payload["pageTitle"], "Example")
        self.assertEqual(payload["textLength"], 512)

    def test_build_fallback_summary_prefers_summary_and_preview(self) -> None:
        article = {
            "title": "Headline",
            "summary": "First summary sentence about guidance and margin expansion.",
        }

        bullets = build_fallback_summary(article, preview_text="Preview text from extracted article.")

        self.assertEqual(len(bullets), 2)
        self.assertIn("guidance", bullets[0])
        self.assertIn("Preview text", bullets[1])

    def test_summarize_article_markdown_falls_back_without_llm(self) -> None:
        article = {
            "title": "Headline",
            "summary": "Feed summary",
            "link": "https://example.com/article",
        }

        bullets, mode = summarize_article_markdown(
            article,
            "# Headline\n\nDetailed markdown article body.",
            llm_provider=None,
            preview_text="Extracted preview",
        )

        self.assertEqual(mode, "fallback")
        self.assertGreaterEqual(len(bullets), 1)

    def test_enrich_news_records_failures_when_playwright_server_cannot_start(self) -> None:
        article = {
            "title": "Apple earnings beat expectations",
            "summary": "Apple reported stronger revenue guidance.",
            "link": "https://example.com/apple-earnings",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("news.enrichment.make_playwright_server", return_value=FailingServer()):
                enrichment = asyncio.run(
                    _enrich_news_async(
                        {"agents": {"tools_enabled": True}},
                        ticker="AAPL",
                        company_name="Apple Inc.",
                        news_items=[article],
                        artifacts_dir=Path(tmpdir),
                        llm_provider=None,
                    )
                )

        self.assertEqual(enrichment["status"]["selected_count"], 1)
        self.assertEqual(enrichment["status"]["deep_read_count"], 0)
        self.assertEqual(enrichment["status"]["failed_count"], 1)
        self.assertIn("MCP startup failed", enrichment["failures"][0]["error"])


if __name__ == "__main__":
    unittest.main()
