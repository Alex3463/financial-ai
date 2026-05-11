from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_pipeline import _effective_use_judge  # noqa: E402


class RunPipelineConfigTests(unittest.TestCase):
    def test_skip_llm_disables_default_judge_without_explicit_judge_flag(self) -> None:
        cfg = {"eval": {"use_llm_judge": True}}
        args = argparse.Namespace(skip_llm=True, judge=False, no_judge=False)

        self.assertFalse(_effective_use_judge(cfg, args))

    def test_explicit_judge_still_overrides_skip_llm_for_keyed_environments(self) -> None:
        cfg = {"eval": {"use_llm_judge": False}}
        args = argparse.Namespace(skip_llm=True, judge=True, no_judge=False)

        self.assertTrue(_effective_use_judge(cfg, args))


if __name__ == "__main__":
    unittest.main()
