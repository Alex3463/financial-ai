from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tiktoken
from jinja2 import Environment, FileSystemLoader, select_autoescape


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class ContextBuilder:
    TOKEN_LIMIT = 5000

    def build(self, snapshot: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
        info = snapshot["info"]
        return {
            "metadata": {
                "ticker": snapshot["ticker"],
                "company_name": info.get("longName") or snapshot["ticker"],
                "sector": info.get("sector") or "N/A",
                "industry": info.get("industry") or "N/A",
                "report_date": today_str(),
                "data_as_of": snapshot["fetched_at"],
            },
            "price_summary": {
                "current_price": snapshot["price"]["current"],
                "52w_high": snapshot["price"]["52w_high"],
                "52w_low": snapshot["price"]["52w_low"],
                "returns": {k: v for k, v in features.items() if str(k).startswith("return_")},
                "vol_annual": features.get("vol_annual"),
            },
            "valuation": features["valuation"],
            "financials": {
                "quarterly_trend": self._last_4q_summary(snapshot["financials"]["income_stmt"]),
                "growth_rates": features["growth"],
                "health": features["health"],
            },
            "news_summary": {
                "recent_headlines": [n.get("title", "") for n in snapshot["news"][:5]],
                "sentiment": features["sentiment"],
            },
            "analyst_consensus": snapshot["analyst_recs"],
        }

    def check_token_budget(self, context: dict[str, Any], model: str = "gpt-4o") -> dict[str, Any]:
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        tokens = len(enc.encode(json.dumps(context, ensure_ascii=False)))
        return {
            "context_tokens": tokens,
            "within_budget": tokens <= self.TOKEN_LIMIT,
            "warning": None if tokens <= self.TOKEN_LIMIT else f"컨텍스트 {tokens} tokens → 요약 필요",
        }

    def _last_4q_summary(self, income: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(income, dict):
            return []
        rev = income.get("Total Revenue") or {}
        op = income.get("Operating Income") or {}
        net = income.get("Net Income") or {}
        if not isinstance(rev, dict):
            return []
        dates = sorted(rev.keys(), reverse=True)[:4]
        rows: list[dict[str, Any]] = []
        for d in dates:
            rows.append(
                {
                    "quarter": d,
                    "revenue": rev.get(d),
                    "op_income": op.get(d) if isinstance(op, dict) else None,
                    "net_income": net.get(d) if isinstance(net, dict) else None,
                }
            )
        return rows


def render_report_prompt(
    prompts_dir: Path,
    context: dict[str, Any],
    template_name: str = "report.j2",
) -> tuple[str, str]:
    env = Environment(
        loader=FileSystemLoader(str(prompts_dir)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template(template_name)
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    rendered = tmpl.render(context=context, context_json=context_json, metadata=context["metadata"])
    sep = "---SYSTEM---"
    if sep in rendered:
        system_part, user_part = rendered.split(sep, 1)
        return system_part.strip(), user_part.strip()
    return "", rendered.strip()


def compose_markdown_report(
    llm: Any,
    prompts_dir: Path,
    context: dict[str, Any],
) -> str:
    system_msg, user_msg = render_report_prompt(prompts_dir, context)
    if not system_msg:
        system_msg = (
            "당신은 CFA 자격증을 보유한 금융 애널리스트입니다. "
            "제공된 데이터만 사용하고, 숫자에는 반드시 출처 태그를 붙이세요."
        )
    return llm.generate(system_msg, user_msg)
