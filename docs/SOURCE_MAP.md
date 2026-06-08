# 소스코드 구성 (SOURCE MAP)

「소스코드는 어떻게 나뉘어 있나?」 질문용 **디렉터리 트리**와 주요 파일 역할입니다.  
개발 시 수정 포인트는 [ONBOARDING.md](ONBOARDING.md) 4~5절을 참고하세요.

---

## 루트 트리 (요약)

```
financial-ai/
├── README.md                 # 사용자·운영 문서 (실행·옵션·문제해결)
├── config.yaml               # LLM·MCP·ingest·eval·paths 설정
├── pyproject.toml            # Python 의존성 (uv)
├── uv.lock                   # 의존성 잠금
├── .python-version           # Python 3.12
│
├── docs/
│   ├── README.md             # 발표 문서 인덱스
│   ├── ARCHITECTURE.md       # 아키텍처·다이어그램
│   ├── FEATURES.md           # 기능 목록
│   ├── DEMO_GUIDE.md         # 발표 데모 가이드
│   ├── SOURCE_MAP.md         # 본 문서
│   └── ONBOARDING.md         # 개발자 온보딩 (코드 수정 가이드)
│
├── scripts/                  # ★ 사람이 실행하는 진입점
│   ├── run_pipeline.py       # 메인 파이프라인 (단일·배치)
│   ├── run_dashboard.py      # 웹 데모 서버 (uvicorn)
│   ├── list_gateway_models.py
│   └── deploy_local.sh       # launchd 백그라운드 배포
│
├── src/                      # ★ 도메인 라이브러리 (직접 실행 X)
│   ├── ingest/
│   ├── news/
│   ├── features/
│   ├── report/
│   ├── agents/
│   ├── eval/
│   ├── trading_stub/
│   ├── fio/
│   └── web/
│
├── prompts/                  # legacy 리포트·Judge Jinja 템플릿
├── api_guide/                # .env 템플릿 (키 커밋 금지)
├── launchd/                  # macOS 서비스 plist 템플릿
├── tests/                    # pytest 단위·통합 테스트
│
├── artifacts/                # [산출물] 티커/날짜별 JSON·sections
├── reports/                  # [산출물] Markdown 리포트
├── tracking/                 # [산출물] prediction_log.csv
└── logs/                     # [로컬] 모델 목록·대시보드 URL·stdout
```

**굵은 역할**: `scripts/` = 진입점, `src/` = 비즈니스 로직, 나머지 폴더 = 설정·문서·산출물.

---

## `scripts/` — 실행 진입점

| 파일 | 역할 |
|------|------|
| `run_pipeline.py` | `run_single_pipeline()` — 5단계 오케스트레이션, CLI 인자, 배치 루프 |
| `run_dashboard.py` | uvicorn 기동, `--public` / `--lan` / cloudflared 터널 |
| `list_gateway_models.py` | 게이트웨이 `/models` 조회 → `logs/` 저장 |
| `deploy_local.sh` | `uv sync`, 웹 테스트, launchd 등록 (`--public`) |

---

## `src/ingest/` — 데이터 수집

| 파일 | 역할 |
|------|------|
| `yahoo.py` | `YahooIngester` — yfinance로 가격·info·뉴스·funds_data 등 `snapshot.json` 스키마 |

---

## `src/news/` — 뉴스 enrich

| 파일 | 역할 |
|------|------|
| `enrichment.py` | 뉴스 후보 선정, Playwright MCP deep-read, digest·`news_enrichment.json` |

---

## `src/features/` — 파생 피처

| 파일 | 역할 |
|------|------|
| `builder.py` | `FeatureBuilder` — 수익률, 밸류, VIX, 기술·거래량 지표 |

---

## `src/report/` — 컨텍스트·legacy LLM

| 파일 | 역할 |
|------|------|
| `composer.py` | `ContextBuilder` — snapshot+features+뉴스 → `context.json`; legacy `compose_markdown_report` |
| `llm.py` | `LLMProvider` — OpenAI 호환 클라이언트, 키·UA, 모델 목록 조회 |

---

## `src/agents/` — Agents 리포트 (기본 경로)

| 파일/폴더 | 역할 |
|-----------|------|
| `orchestrator.py` | `run_agent_report()` — 슬라이스·도메인 에이전트·컴포저·postcheck·ETF 분기 |
| `context_slicer.py` | `context.json` → valuation/financials/growth/risk/etf 슬라이스 |
| `valuation_agent.py` | 밸류에이션 에이전트 |
| `financials_agent.py` | 재무 에이전트 |
| `growth_agent.py` | 성장 에이전트 |
| `risk_agent.py` | 리스크 에이전트 |
| `holdings_agent.py` | ETF 보유 종목 에이전트 |
| `composer_agent.py` | 일반 주식 최종 Markdown 합성 |
| `etf_composer_agent.py` | ETF 전용 합성 |
| `postcheck.py` | 리포트 계약 검증 (일반·ETF) |
| `mcp_servers.py` | Playwright / yfinance MCP stdio 서버 팩토리 |
| `gateway.py` | Agents SDK 게이트웨이 설정 |
| `schemas.py` | Pydantic 입·출력 스키마 |
| `prompts/*.md` | 에이전트별 시스템 지시문 |

---

## `src/eval/` — 평가

| 파일 | 역할 |
|------|------|
| `rules.py` | M0 규칙 채점 (출처·리스크·예측·ETF 항목) |
| `judge.py` | M2 LLM Judge 6항목 |
| `rubric.py` | `aggregate()` — 총점·등급·M0/M2 모드 |
| `number_scan.py` | 리포트 숫자·context 교차 검사 보조 |

---

## `src/trading_stub/` — 신호 스텁

| 파일 | 역할 |
|------|------|
| `signal.py` | 리포트에서 의견 추출 → `signal.json`, CSV row 형식 |

---

## `src/fio/` — 저장 유틸

| 파일 | 역할 |
|------|------|
| `storage.py` | `write_json`, `append_prediction_row` 등 |

---

## `src/web/` — 데모 대시보드

| 파일 | 역할 |
|------|------|
| `app.py` | FastAPI 라우트 (`/api/analyze`, `/api/jobs`, …) |
| `pipeline_runner.py` | `run_for_dashboard()`, `load_existing_run()`, `list_history()` |
| `jobs.py` | 백그라운드 Job 큐·폴링 상태 |
| `cache.py` | `is_complete_run()` — 캐시 히트 판별 |
| `tunnel.py` | cloudflared quick tunnel |
| `access_log.py` | 방문자 IP·요청 로그 |
| `static/index.html` | UI 셸 |
| `static/app.js` | 탭·폼·Job 폴링·렌더링 |
| `static/report_parser.js` | Markdown 파싱 |
| `static/chart_view.js` | Lightweight Charts |
| `static/style.css` | 스타일 |

---

## `prompts/` — Legacy·Judge 템플릿

| 파일 | 역할 |
|------|------|
| `report.j2` | legacy 단일 호출 리포트 프롬프트 |
| `judge.j2` | LLM Judge 프롬프트 |

---

## `tests/` — 테스트

| 파일 | 검증 대상 |
|------|-----------|
| `test_run_pipeline.py` | 파이프라인 통합 |
| `test_web_dashboard.py` | 대시보드 API |
| `test_web_cache.py` | 캐시 완료 판별 |
| `test_agents_orchestrator.py` | Agents 오케스트레이션 |
| `test_postcheck.py` | 리포트 계약 |
| `test_news_enrichment.py` | 뉴스 enrich |
| `test_yahoo_ingester.py` | 수집 |
| `test_eval_etf.py` | ETF 평가 |
| 기타 | composer, features, MCP, community 등 |

---

## 산출물 경로 규칙

```
artifacts/<TICKER>/<YYYY-MM-DD>/
  snapshot.json
  news_enrichment.json
  news/*.md
  context.json
  eval.json
  signal.json
  sections/          # agents 모드만
    context_slices.json
    valuation.json
    financials.json
    …
    composer_output.json

reports/<TICKER>/<YYYY-MM-DD>.md

tracking/prediction_log.csv

artifacts/_batch/<YYYY-MM-DD>/   # 배치 요약
  batch_summary.json
  errors.json                    # 실패 시
```

---

## 설정·비밀 정보

| 경로 | 역할 |
|------|------|
| `config.yaml` | 비밀 없음, 커밋 가능 |
| `.env` / `api_guide/.env` | `OPENAI_API_KEY` — **git 제외** |
| `logs/dashboard.public_url` | 최신 공개 터널 URL (로컬) |

---

## 관련 문서

- [ARCHITECTURE.md](ARCHITECTURE.md) — 흐름·다이어그램
- [ONBOARDING.md](ONBOARDING.md) — 「이걸 바꾸고 싶다」 매핑
