from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ingest.yahoo import (  # noqa: E402
    _clean_community_body,
    _fetch_yahoo_community,
    _posts_from_gql_edges,
)

SAMPLE_GQL_RESPONSE = {
    "data": {
        "getContentByAssociatedContentId": {
            "newFeed": {
                "edges": [
                    {
                        "node": {
                            "uuid": "abc-1",
                            "contentType": "POST",
                            "body": "## Bullish breakout\nTSLA to the moon",
                            "createdAt": "2026-06-08T14:00:00Z",
                            "user": {"profile": {"username": "trader1", "name": "Trader"}},
                            "votes": {"upvoteCount": 3},
                            "comments": {"count": 1},
                        }
                    },
                    {
                        "node": {
                            "uuid": "abc-2",
                            "contentType": "TRADE",
                            "body": "ignored",
                        }
                    },
                ]
            }
        }
    }
}


class YahooCommunityTests(unittest.TestCase):
    def test_clean_community_body_strips_markdown_images(self) -> None:
        raw = "![](https://example.com/img.png) Real text here"
        self.assertEqual(_clean_community_body(raw), "Real text here")

    def test_posts_from_gql_edges_maps_post_nodes(self) -> None:
        edges = SAMPLE_GQL_RESPONSE["data"]["getContentByAssociatedContentId"]["newFeed"]["edges"]
        posts = _posts_from_gql_edges(edges, max_items=10)
        self.assertEqual(len(posts), 1)
        self.assertIn("Bullish breakout", posts[0]["text"])
        self.assertEqual(posts[0]["author"], "Trader")
        self.assertEqual(posts[0]["upvotes"], 3)
        self.assertEqual(posts[0]["comment_count"], 1)

    @patch("ingest.yahoo._fetch_yahoo_community_gql")
    @patch("ingest.yahoo._message_board_id", return_value="finmb_24937")
    def test_fetch_yahoo_community_ok(self, _board: object, mock_gql: object) -> None:
        mock_gql.return_value = [{"text": "buy the dip", "author": "alice", "upvotes": 2}]
        out = _fetch_yahoo_community("AAPL", max_items=5, message_board_id="finmb_24937")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["n_items"], 1)
        self.assertEqual(out["fetch_method"], "graphql")
        self.assertEqual(out["message_board_id"], "finmb_24937")
        self.assertEqual(out["conversations"][0]["text"], "buy the dip")

    @patch("ingest.yahoo._message_board_id", return_value="")
    def test_fetch_yahoo_community_missing_board(self, _board: object) -> None:
        out = _fetch_yahoo_community("INVALID", max_items=5)
        self.assertEqual(out["status"], "error")
        self.assertIn("messageBoardId", out.get("error", ""))


if __name__ == "__main__":
    unittest.main()
