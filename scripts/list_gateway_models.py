#!/usr/bin/env python3
"""게이트웨이에서 사용 가능한 모델만 조회해 logs/ 에 저장합니다."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "api_guide" / ".env")

import yaml

from report.llm import write_gateway_models_log


def main() -> None:
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_project_root"] = str(ROOT)
    _, err, log_text = write_gateway_models_log(ROOT, cfg)
    print(log_text)
    print(f"(저장됨: {ROOT / 'logs' / 'available_models_latest.txt'})")
    raise SystemExit(1 if err else 0)


if __name__ == "__main__":
    main()
