from __future__ import annotations

import asyncio
import contextlib
import io
import sys
import unittest
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.orchestrator import _maybe_enter_server  # noqa: E402


class FailingMcpServer:
    async def __aenter__(self) -> "FailingMcpServer":
        raise TimeoutError("startup timed out")

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class AgentOrchestratorTests(unittest.TestCase):
    def test_maybe_enter_server_falls_back_when_yfinance_mcp_startup_fails(self) -> None:
        async def run_case() -> tuple[object | None, str]:
            output = io.StringIO()
            with patch("agents.orchestrator.make_yfinance_server", return_value=FailingMcpServer()):
                async with AsyncExitStack() as exit_stack:
                    with contextlib.redirect_stdout(output):
                        server = await _maybe_enter_server(
                            exit_stack,
                            {},
                            name="yfinance-valuation",
                        )
            return server, output.getvalue()

        server, output = asyncio.run(run_case())

        self.assertIsNone(server)
        self.assertIn("[pipeline] [경고]", output)
        self.assertIn("yfinance-valuation", output)
        self.assertIn("도구 없이 계속", output)


if __name__ == "__main__":
    unittest.main()
