#!/usr/bin/env python3
"""티커 하나에 대해 수집 → 리포트 → 평가 → 신호까지 실행합니다."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "api_guide" / ".env")

import yaml

from eval.judge import run_llm_judge
from eval.rubric import aggregate
from eval.rules import run_all_checks
from features.builder import FeatureBuilder
from ingest.yahoo import YahooIngester
from news.enrichment import enrich_news
from fio.storage import append_prediction_row, write_json
from report.composer import ContextBuilder, compose_markdown_report, today_str
from report.llm import LLMProvider, write_gateway_models_log
from trading_stub.signal import extract_signal_from_report, trading_signal_to_json


def _plog(msg: str) -> None:
    """콘솔 진행 로그 (간단한 흐름 표시)."""
    print(f"[pipeline] {msg}", flush=True)


def load_config() -> dict:
    path = ROOT / "config.yaml"
    with path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_project_root"] = str(ROOT)
    return cfg


def paths_for_date(cfg: dict, ticker: str, date_str: str) -> dict[str, Path]:
    base_a = Path(cfg.get("paths", {}).get("artifacts", "artifacts"))
    base_r = Path(cfg.get("paths", {}).get("reports", "reports"))
    base_t = Path(cfg.get("paths", {}).get("tracking", "tracking"))
    if not base_a.is_absolute():
        base_a = ROOT / base_a
    if not base_r.is_absolute():
        base_r = ROOT / base_r
    if not base_t.is_absolute():
        base_t = ROOT / base_t
    art_dir = base_a / ticker / date_str
    report_dir = base_r / ticker
    report_dir.mkdir(parents=True, exist_ok=True)
    art_dir.mkdir(parents=True, exist_ok=True)
    base_t.mkdir(parents=True, exist_ok=True)
    return {
        "artifacts_dir": art_dir,
        "report_md": report_dir / f"{date_str}.md",
        "tracking_csv": base_t / "prediction_log.csv",
    }


def extract_target_price(report_text: str) -> str:
    m = re.search(r"목표가[^\d]{0,50}[\$₩￦]?\s*([\d,.]+)", report_text)
    if m:
        return m.group(1).replace(",", "")
    return ""


def extract_horizon_text(report_text: str) -> str:
    hm = re.search(r"(12개월|6개월|3개월|1개월)", report_text)
    return hm.group(1) if hm else ""


def _rel_report_path(report_md: Path) -> str:
    try:
        return str(report_md.relative_to(ROOT))
    except ValueError:
        return str(report_md)


def _stub_report(ticker: str, context: dict) -> str:
    """로컬 검증용 최소 Markdown (섹션·키워드 포함)."""
    meta = context.get("metadata", {})
    name = meta.get("company_name", ticker)
    per = context.get("valuation", {}).get("PER", "N/A")
    return f"""# {ticker} ({name}) 투자 분석 리포트

### 1. 투자 요약
- **투자 의견**: 중립
- 목표가 $200 (PER 기반 단순 추정)
- 투자 기간: 12개월

### 2. 재무 현황
- trailing PER 약 {per} [출처: yf.info.trailingPE, {meta.get("data_as_of", "")}]

### 3. 성장 동력
- 서비스 매출 성장
- 단위당 마진 개선

### 4. 리스크 요인
- 경쟁 심화
- 규제 강화
- 금리 상승 시 멀티플 하락

### 5. 밸류에이션
- PER 배수 적용: 목표가 = EPS × PER 26 [출처: 단순 배수 가정]

### 6. 투자 결론
- 12개월 관점 중립. 멀티플 수축 시 하방 위험.
"""


def _effective_use_judge(cfg: dict, args: argparse.Namespace) -> bool:
    if getattr(args, "no_judge", False):
        return False
    if getattr(args, "judge", False):
        return True
    return bool(cfg.get("eval", {}).get("use_llm_judge", False))


def _resolve_tickers(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    xs: list[str] = []
    if args.ticker:
        # --ticker 를 단일 문자열로 쓰거나, --ticker AAPL TSLA NVDA 처럼 여러 개를 받을 수 있게 허용
        if isinstance(args.ticker, list):
            xs.extend([t.strip().upper() for t in args.ticker if str(t).strip()])
        else:
            xs.append(str(args.ticker).strip().upper())
    if getattr(args, "tickers", None):
        xs.extend([t.strip().upper() for t in args.tickers.split(",") if t.strip()])
    if getattr(args, "tickers_file", None):
        p = Path(args.tickers_file)
        if not p.is_file():
            parser.error(f"--tickers-file 을 찾을 수 없습니다: {p}")
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                xs.append(line.upper())
    seen: set[str] = set()
    out: list[str] = []
    for t in xs:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def run_single_pipeline(
    cfg: dict,
    ticker: str,
    date_str: str,
    args: argparse.Namespace,
    *,
    emit_model_log: bool = True,
) -> None:
    """단일 티커 end-to-end (배치에서도 재사용)."""
    llm_cfg = cfg.get("llm", {})
    model_hint = os.environ.get("FINANCIAL_AI_MODEL") or llm_cfg.get("model", "?")
    use_judge = _effective_use_judge(cfg, args)

    _plog(f"시작: ticker={ticker}, date={date_str}")
    _plog(
        "분기: "
        + ("--skip-llm (더미 리포트)" if args.skip_llm else f"LLM 리포트 (model={model_hint})")
        + (" | --model-log" if args.model_log and emit_model_log else "")
        + (" | LLM Judge(M2)" if use_judge else "")
    )

    if emit_model_log and args.model_log:
        _plog("선택: 게이트웨이 모델 목록 조회 중…")
        _, err, log_text = write_gateway_models_log(ROOT, cfg)
        print(log_text)
        print(f"(저장됨: {ROOT / 'logs' / 'available_models_latest.txt'})")
        if err:
            print(f"[pipeline] [경고] 모델 목록 조회 실패: {err}")

    paths = paths_for_date(cfg, ticker, date_str)
    _plog(f"경로: artifacts={paths['artifacts_dir']} | report={paths['report_md']}")

    _plog("1/5 데이터 수집 (yfinance)…")
    ingester = YahooIngester()
    snapshot = ingester.fetch(ticker, cfg)
    write_json(paths["artifacts_dir"] / "snapshot.json", snapshot)
    _plog(f"  → snapshot.json 저장 (종가≈{snapshot['price']['current']})")
    news_enrichment = enrich_news(
        cfg,
        ticker=ticker,
        company_name=str(snapshot.get("info", {}).get("longName") or ticker),
        news_items=list(snapshot.get("news", [])),
        artifacts_dir=paths["artifacts_dir"],
        use_llm_summary=not args.skip_llm,
    )
    status = news_enrichment.get("status", {})
    _plog(
        "  → 뉴스 심층 읽기: "
        f"{status.get('deep_read_count', 0)}/{status.get('selected_count', 0)}건 성공"
        + (
            f", 실패 {status.get('failed_count', 0)}건"
            if status.get("failed_count", 0)
            else ""
        )
    )

    _plog("2/5 피처·컨텍스트…")
    fb = FeatureBuilder()
    features = fb.build(snapshot)
    cb = ContextBuilder()
    context = cb.build(snapshot, features, news_enrichment)
    write_json(paths["artifacts_dir"] / "context.json", context)

    budget = cb.check_token_budget(context)
    context["_token_check"] = budget
    tok = budget.get("context_tokens", "?")
    ok_budget = budget.get("within_budget", False)
    _plog(f"  → context.json 저장 | 추정 토큰≈{tok} (예산 내: {ok_budget})")

    prompts_rel = Path(cfg.get("paths", {}).get("prompts", "prompts"))
    prompts_dir = prompts_rel if prompts_rel.is_absolute() else ROOT / prompts_rel

    llm_report: LLMProvider | None = None
    llm_mode = (cfg.get("llm", {}).get("mode") or "agents").lower()
    if args.skip_llm:
        _plog("3/5 리포트: 분기 → --skip-llm, 내장 스텁 Markdown 사용")
        report_md = _stub_report(ticker, context)
        paths["report_md"].write_text(report_md, encoding="utf-8")
    elif llm_mode == "agents":
        _plog("3/5 리포트: Agents (OpenAI Agents SDK)…")
        from agents.orchestrator import run_agent_report

        report_md = run_agent_report(cfg, context)
        paths["report_md"].write_text(report_md, encoding="utf-8")
    else:
        _plog("3/5 리포트: LLM 단일 호출 (legacy)…")
        llm_report = LLMProvider(cfg)
        report_md = compose_markdown_report(llm_report, prompts_dir, context)
        paths["report_md"].write_text(report_md, encoding="utf-8")
    _plog(f"  → {paths['report_md'].name} 저장 ({len(report_md)} chars)")

    _plog("4/5 규칙 평가 + (선택) LLM Judge…")
    rule_scores = run_all_checks(report_md, context)
    judge_scores = None
    judge_flags: list[str] = []
    if use_judge:
        _plog("  → LLM Judge 호출 (루브릭 6항목)…")
        judge_llm = llm_report or LLMProvider(cfg)
        try:
            judge_scores, judge_flags = run_llm_judge(
                report_md, context, judge_llm, prompts_dir, cfg
            )
        except Exception as e:
            _plog(f"  [경고] Judge 실패 — 규칙 점수만 사용: {e}")
            judge_flags = [f"Judge 오류: {e}"]

    agg = aggregate(rule_scores, judge_scores)
    agg["flags"] = list(agg.get("flags", [])) + judge_flags
    eval_out = {
        "ticker": ticker,
        "report_date": date_str,
        **agg,
    }
    write_json(paths["artifacts_dir"] / "eval.json", eval_out)
    n_flags = len(agg.get("flags") or [])
    _plog(
        f"  → total={agg['total_score']} | {agg.get('rubric_mode', '')} | "
        f"{agg.get('auto_coverage', '')} | 플래그 {n_flags}건"
    )

    _plog("5/5 신호·트래킹 CSV…")
    tsig = extract_signal_from_report(
        report_md,
        agg,
        ticker,
        _rel_report_path(paths["report_md"]),
        date_str,
    )
    sig_json = trading_signal_to_json(tsig)
    write_json(paths["artifacts_dir"] / "signal.json", sig_json)

    price_at = snapshot["price"]["current"]
    row = {
        "date": date_str,
        "ticker": ticker,
        "price_at_report": price_at,
        "opinion": tsig.signal,
        "target_price": extract_target_price(report_md),
        "horizon": extract_horizon_text(report_md),
        "confidence": tsig.confidence,
        "rubric_score": agg["total_score"],
        "3m_actual_price": "",
        "12m_actual_price": "",
        "direction_hit_3m": "",
        "direction_hit_12m": "",
        "excess_return_vs_sp500": "",
        "target_hit": "",
        "pe_reported": "",
        "pe_actual": snapshot["info"].get("trailingPE", ""),
        "data_accuracy_flag": "",
    }
    fieldnames = list(row.keys())
    append_prediction_row(paths["tracking_csv"], row, fieldnames)
    _plog(f"  → signal.json + {paths['tracking_csv'].name} 1행 추가")

    _plog("전 단계 완료.")
    print(f"완료: {paths['report_md']}")
    note = agg.get("grade_note", "")
    if note:
        print(f"등급 설명: {note}")
    print(
        f"eval 원점수: {agg['total_score']} | 환산≈{agg.get('score_normalized_100', agg['total_score'])}/100 | 등급: {agg['grade']}"
    )
    print(f"신호: {tsig.signal} (confidence={tsig.confidence})")


def _run_batch(cfg: dict, tickers: list[str], date_str: str, args: argparse.Namespace) -> None:
    sleep_s = float(cfg.get("ingest", {}).get("sleep_between_tickers", 1))
    batch_dir = ROOT / "artifacts" / "_batch" / date_str
    batch_dir.mkdir(parents=True, exist_ok=True)

    if args.model_log:
        _plog("배치: 시작 전 게이트웨이 모델 목록 1회 조회")
        _, err, log_text = write_gateway_models_log(ROOT, cfg)
        print(log_text)
        if err:
            print(f"[pipeline] [경고] 모델 목록 조회 실패: {err}")

    ok: list[str] = []
    failed: list[dict[str, str]] = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            _plog(f"배치: yfinance 간격 {sleep_s}s")
            time.sleep(sleep_s)
        _plog(f"======== 배치 [{i + 1}/{len(tickers)}] {ticker} ========")
        try:
            run_single_pipeline(cfg, ticker, date_str, args, emit_model_log=False)
            ok.append(ticker)
        except Exception as e:
            err = {"ticker": ticker, "error": str(e), "type": type(e).__name__}
            failed.append(err)
            _plog(f"[오류] {ticker}: {e}")

    summary = {"date": date_str, "success": ok, "failed": failed, "total": len(tickers)}
    write_json(batch_dir / "batch_summary.json", summary)
    if failed:
        write_json(batch_dir / "errors.json", {"errors": failed})
    _plog(
        f"배치 종료: 성공 {len(ok)}/{len(tickers)}, 실패 {len(failed)} — "
        f"{batch_dir / 'batch_summary.json'}"
    )
    raise SystemExit(1 if failed else 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="금융AI 파이프라인 (M0/M2, 단일·배치)")
    parser.add_argument(
        "--ticker",
        nargs="+",
        default=None,
        help="티커 1개 또는 여러 개: --ticker AAPL  /  --ticker AAPL TSLA NVDA",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="쉼표 구분 다종목: AAPL,MSFT,GOOG",
    )
    parser.add_argument(
        "--tickers-file",
        default=None,
        metavar="PATH",
        help="한 줄에 하나씩 티커 (# 주석 가능)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="아티팩트 날짜 폴더 (기본: 오늘 UTC 기준 YYYY-MM-DD)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="LLM 리포트 생략(스텁). Judge는 config/플래그에 따라 별도 호출 가능",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="게이트웨이 모델 목록만 조회 후 종료",
    )
    parser.add_argument(
        "--model-log",
        action="store_true",
        help="실행 시(또는 배치 시작 시 1회) 모델 목록 조회·logs 저장",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="config와 무관하게 이번 실행만 LLM Judge(M2) 켜기",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="이번 실행만 Judge 끄기 (config의 use_llm_judge 무시)",
    )
    args = parser.parse_args()

    cfg = load_config()

    if args.list_models:
        _plog("분기: --list-models (모델 목록만 조회 후 종료)")
        _, err, log_text = write_gateway_models_log(ROOT, cfg)
        print(log_text)
        print(f"(저장됨: {ROOT / 'logs' / 'available_models_latest.txt'})")
        raise SystemExit(1 if err else 0)

    tickers = _resolve_tickers(args, parser)
    if not tickers:
        parser.error(
            "--ticker, --tickers, --tickers-file 중 하나 이상 필요합니다 (--list-models 제외)."
        )

    if args.ticker and (args.tickers or args.tickers_file):
        parser.error("--ticker 와 --tickers / --tickers-file 은 동시에 사용하지 마세요.")

    date_str = args.date or today_str()

    if len(tickers) > 1:
        _run_batch(cfg, tickers, date_str, args)
        return

    run_single_pipeline(cfg, tickers[0], date_str, args, emit_model_log=True)


if __name__ == "__main__":
    main()
