from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.schemas import RiskItem  # noqa: E402


class AgentSchemaTests(unittest.TestCase):
    def test_risk_description_has_concise_length_limit(self) -> None:
        with self.assertRaises(ValidationError):
            RiskItem(category="경쟁", description="가" * 321, citations=["source"])

    def test_risk_prompt_mentions_description_length_limit(self) -> None:
        prompt = (SRC / "agents" / "prompts" / "risk.md").read_text(encoding="utf-8")

        self.assertIn("320자", prompt)


if __name__ == "__main__":
    unittest.main()
