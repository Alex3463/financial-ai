"""M2: LLM Judge — 루브릭 6항목(데이터·재무·밸류·논리·편향·가독성) 채점."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

JUDGE_KEYS = (
    "data_accuracy",
    "financial_quality",
    "valuation_soundness",
    "logic_consistency",
    "bias_check",
    "readability",
)

JUDGE_CAPS = {
    "data_accuracy": 20,
    "financial_quality": 15,
    "valuation_soundness": 20,
    "logic_consistency": 10,
    "bias_check": 5,
    "readability": 5,
}


def render_judge_prompt(
    prompts_dir: Path,
    report_text: str,
    context: dict[str, Any],
    template_name: str = "judge.j2",
) -> tuple[str, str]:
    env = Environment(
        loader=FileSystemLoader(str(prompts_dir)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template(template_name)
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    rendered = tmpl.render(report=report_text, context_json=context_json)
    sep = "---SYSTEM---"
    if sep not in rendered:
        return (
            "당신은 금융 리포트 심사위원입니다. JSON만 출력하세요.",
            rendered.strip(),
        )
    system_part, user_part = rendered.split(sep, 1)
    return system_part.strip(), user_part.strip()


def _parse_judge_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"Judge 응답에서 JSON을 찾을 수 없습니다: {raw[:500]}")
        return json.loads(text[start : end + 1])


def _clamp_judge_scores(data: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in JUDGE_KEYS:
        cap = JUDGE_CAPS[k]
        raw_v = data.get(k)
        if raw_v is None:
            out[k] = 0
            continue
        try:
            x = int(round(float(raw_v)))
        except (TypeError, ValueError):
            x = 0
        out[k] = max(0, min(cap, x))
    return out


def run_llm_judge(
    report_text: str,
    context: dict[str, Any],
    llm: Any,
    prompts_dir: Path,
    config: dict[str, Any],
) -> tuple[dict[str, int], list[str]]:
    """
    LLM Judge 호출 → 6항목 점수 dict, 플래그(요약 문구 등).
    """
    eval_cfg = config.get("eval", {})
    j_max = int(eval_cfg.get("judge_max_tokens", 2048))
    j_temp = float(eval_cfg.get("judge_temperature", 0.15))

    system_msg, user_msg = render_judge_prompt(prompts_dir, report_text, context)
    raw = llm.generate(system_msg, user_msg, max_tokens=j_max, temperature=j_temp)
    payload = _parse_judge_json(raw)
    scores = _clamp_judge_scores(payload)

    flags: list[str] = []
    rationale = payload.get("brief_rationale")
    if isinstance(rationale, str) and rationale.strip():
        flags.append(f"Judge: {rationale.strip()[:300]}")

    return scores, flags
