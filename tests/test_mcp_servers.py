from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.mcp_servers import (  # noqa: E402
    _merged_playwright_config,
    _merged_yfinance_config,
    make_yfinance_server,
)


class McpServerConfigTests(unittest.TestCase):
    def test_yfinance_config_uses_safe_startup_timeout_by_default(self) -> None:
        merged = _merged_yfinance_config({})

        self.assertEqual(merged["client_session_timeout_seconds"], 30.0)
        self.assertEqual(merged["max_retry_attempts"], 1)

    def test_yfinance_config_preserves_explicit_timeout_and_retry(self) -> None:
        cfg = {
            "mcp": {
                "yfinance": {
                    "command": "python",
                    "args": ["-m", "example"],
                    "client_session_timeout_seconds": 45,
                    "max_retry_attempts": 2,
                }
            },
        }

        merged = _merged_yfinance_config(cfg)

        self.assertEqual(merged["client_session_timeout_seconds"], 45.0)
        self.assertEqual(merged["max_retry_attempts"], 2)

    def test_make_yfinance_server_passes_timeout_and_retry_to_stdio_server(self) -> None:
        cfg = {
            "mcp": {
                "yfinance": {
                    "command": "python",
                    "args": ["-m", "example"],
                    "client_session_timeout_seconds": 45,
                    "max_retry_attempts": 2,
                }
            },
        }

        server = make_yfinance_server(cfg, name="test-yfinance")

        self.assertIsNotNone(server)
        self.assertEqual(server.client_session_timeout_seconds, 45.0)
        self.assertEqual(server.max_retry_attempts, 2)

    def test_playwright_npx_uses_project_local_npm_cache_by_default(self) -> None:
        cfg = {
            "_project_root": str(ROOT),
            "mcp": {
                "playwright": {
                    "command": "npx",
                    "args": ["@playwright/mcp@latest"],
                    "output_dir": ".playwright-mcp",
                }
            },
        }

        merged = _merged_playwright_config(cfg)

        self.assertEqual(
            merged["env"]["npm_config_cache"],
            str((ROOT / ".playwright-mcp" / "npm-cache").resolve()),
        )

    def test_playwright_config_preserves_explicit_npm_cache(self) -> None:
        cfg = {
            "_project_root": str(ROOT),
            "mcp": {
                "playwright": {
                    "command": "npx",
                    "args": ["@playwright/mcp@latest"],
                    "env": {"npm_config_cache": "/tmp/custom-npm-cache"},
                }
            },
        }

        merged = _merged_playwright_config(cfg)

        self.assertEqual(merged["env"]["npm_config_cache"], "/tmp/custom-npm-cache")


if __name__ == "__main__":
    unittest.main()
