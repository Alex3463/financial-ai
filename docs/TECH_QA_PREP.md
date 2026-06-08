# 기술 Q&A 준비 — 티커 입력부터 리포트까지

발표 직후 **기술 스택·구현 디테일** 질문에 대비한 쪽집게 자료입니다.  
「어떻게 돌아가나?」「왜 이 기술?」「한계는?」 유형을 중심으로 **예시 질문 → 답** 형태로 정리했습니다.

> 투자 권유가 아닙니다. 본 문서는 시스템 설명용입니다.

---

## 30초 요약 답 (열리는 멘트)

「티커를 넣으면 `scripts/run_pipeline.py`가 **5단계**를 순서대로 돌립니다.  
1단계에서 **yfinance**로 시세·재무·뉴스를 모으고, **Playwright MCP**로 뉴스 본문을 읽은 뒤 **FinBERT**로 감성을 붙입니다.  
2단계에서 숫자 피처를 `context.json`으로 묶고, 3단계에서 **OpenAI Agents SDK**로 밸류·재무·성장·리스크 에이전트가 병렬 분석한 결과를 **Composer**가 6섹션 Markdown 리포트로 합칩니다.  
4단계는 **규칙 채점(M0)** 과 선택적 **LLM Judge(M2)**, 5단계는 리포트에서 **매매 신호 스텁**을 뽑아 `signal.json`과 CSV에 기록합니다.  
웹은 같은 `run_single_pipeline()`을 백그라운드 잡으로 호출하고, 완료된 산출물은 `artifacts/`·`reports/`에서 캐시로 재사용합니다.」

---

## 한눈에 보는 흐름

```
[입력] AAPL / 005930.KS
    │
    ▼
run_pipeline.run_single_pipeline()  ← CLI·웹 공통
    │
    ├─ 1/5 YahooIngester.fetch()        → snapshot.json
    │      enrich_news()               → news_enrichment.json (deep-read + FinBERT)
    │
    ├─ 2/5 FeatureBuilder + ContextBuilder → context.json
    │
    ├─ 3/5 run_agent_report() [agents]  → reports/<티커>/<날짜>.md
    │      (또는 legacy 단일 LLM / --skip-llm 스텁)
    │
    ├─ 4/5 run_all_checks() + run_llm_judge() → eval.json
    │
    └─ 5/5 extract_signal_from_report() → signal.json + prediction_log.csv
```

**웹 경로**: 브라우저 → `POST /api/analyze` → `web/jobs.py` 백그라운드 → `pipeline_runner.run_for_dashboard()` → 위와 동일.

---

## 기술 스택 치트시트

| 영역 | 기술 | 코드 위치 |
|------|------|-----------|
| 런타임 | Python 3.12+, uv | `pyproject.toml` |
| 시세·재무 수집 | yfinance | `src/ingest/yahoo.py` |
| 뉴스 본문 | Playwright MCP (`@playwright/mcp`) | `src/news/enrichment.py` |
| 뉴스 감성 | FinBERT (`ProsusAI/finbert`, transformers+torch) | `src/news/sentiment.py` |
| LLM 리포트 | OpenAI Agents SDK 0.17 + 게이트웨이 API | `src/agents/` |
| 에이전트 도구 | yfinance MCP (`yfmcp`) | `src/agents/mcp_servers.py` |
| 규칙 평가 | 정규식·키워드 루브릭 | `src/eval/rules.py` |
| LLM Judge | 별도 프롬프트 호출 | `src/eval/judge.py` |
| 웹 | FastAPI + Uvicorn + 정적 JS | `src/web/app.py`, `static/` |
| 공개 URL | cloudflared Quick Tunnel | `scripts/run_dashboard.py --public` |

---

## A. 진입점·오케스트레이션

### Q1. CLI와 웹이 같은 파이프라인을 쓰나요?

**A.** 네. 핵심은 `scripts/run_pipeline.py`의 `run_single_pipeline()` 하나입니다. 웹은 `src/web/pipeline_runner.py`의 `run_for_dashboard()`가 같은 함수를 `return_result=True`로 호출합니다. 로그 메시지 `[pipeline] 1/5~5/5`도 동일합니다.

### Q2. 티커 문자열은 어디서 검증하나요?

**A.** 웹 API는 `src/web/security.py`의 `validate_ticker()`로 대문자·허용 문자(영문, 숫자, `.`, `-`)만 통과시킵니다. 한국 종목은 `005930.KS`처럼 Yahoo Finance 심볼 규칙을 그대로 씁니다. CLI는 argparse로 받은 뒤 파이프라인 내부에서 경로에 사용됩니다.

### Q3. 배치(여러 티커)는 어떻게 돌리나요?

**A.** `uv run scripts/run_pipeline.py --tickers "AAPL,TSLA,005930.KS" --date 2026-06-08`처럼 쉼표 구분입니다. 티커마다 `ingest.sleep_between_tickers`(config 기본 1초) 간격을 두고, 요약은 `artifacts/_batch/<날짜>/batch_summary.json`에 남깁니다.

### Q4. `--skip-llm`, `--no-judge`는 무엇을 바꾸나요?

**A.** `--skip-llm`은 3단계에서 API 호출 없이 `_stub_report()` 더미 Markdown을 씁니다(구조 시연용). `--no-judge`는 4단계 LLM Judge를 끄고 규칙 점수(M0)만 씁니다. 발표 전 캐시는 보통 `--no-judge`로 시간을 줄입니다.

### Q5. `config.yaml`의 `llm.mode: agents` vs `legacy` 차이는?

**A.** `agents`(기본): `src/agents/orchestrator.py` → 도메인 에이전트 4개 병렬 + Composer. `legacy`: `src/report/composer.py`의 `compose_markdown_report()`로 **단일 LLM 호출**에 context 전체를 넣습니다. 현재 데모·발표는 agents 모드입니다.

---

## B. 1/5 데이터 수집 (yfinance)

### Q6. snapshot.json에는 무엇이 들어가나요?

**A.** `YahooIngester.fetch()`가 yfinance로 가져온 **현재가·OHLCV·info(재무 비율)·뉴스 헤드라인·애널리스트 목표가·VIX** 등을 한 JSON으로 묶은 것입니다. 경로: `artifacts/<티커>/<날짜>/snapshot.json`.

### Q7. 왜 Bloomberg/Reuters가 아니라 Yahoo인가요?

**A.** 과제·데모 범위에서 **무료·즉시 호출 가능한 공개 API**가 필요했고, yfinance가 티커 하나로 시세·재무·뉴스 헤드라인을 한 번에 줍니다. 상용 데이터 품질·지연 시간은 한계로 인정하고, 리포트에 `[출처:…]`와 규칙 채점으로 투명성을 보완합니다.

### Q8. 한국 종목(005930.KS)은 미국과 동일한가요?

**A.** 파이프라인 구조는 동일합니다. **뉴스**는 Yahoo 헤드라인 부족 시 deep-read 0건이 될 수 있습니다. **종토방**은 GraphQL(`messageBoardId`)로 수집하며, 005930.KS 등은 게시글이 있고 소형 종목(011070.KS)은 `empty`일 수 있습니다.

### Q9. VIX는 왜 넣었나요?

**A.** `config.yaml`의 `ingest.vix_ticker: "^VIX"`로 시장 변동성 레짐을 context에 넣어, 리스크·결론 섹션에서 거시 맥락을 참고하게 합니다. `context.json`의 `market_context.vix`에 저장됩니다.

### Q10. 종토방(community) 데이터는 1/5에 포함되나요?

**A.** `snapshot.json`의 `community` 필드에 Yahoo **GraphQL community API** 결과가 들어갑니다. yfinance `messageBoardId`(예: `finmb_24937`)로 `yfc-server-query.finance.yahoo.com`의 `GetContentByAssociatedContentId` 쿼리를 호출합니다. `/quote/.../community/` HTML은 404이므로 스크래핑이 아닌 API 방식입니다. 게시글이 없는 소형 종목은 `empty`일 수 있습니다.

---

## C. 뉴스 deep-read & FinBERT

### Q11. 헤드라인만 쓰지 않고 왜 본문을 읽나요?

**A.** Yahoo 뉴스는 제목만으로는 맥락이 부족합니다. `enrich_news()`가 상위 N건(`news.max_deep_reads`, 기본 5)을 골라 **Playwright MCP**로 기사 URL을 열고, HTML→Markdown 변환(`markdownify`) 후 본문을 추출합니다. 최소 길이 `MIN_ARTICLE_TEXT_LENGTH=400` 미만이면 실패 처리합니다.

### Q12. 어떤 기사를 우선 deep-read하나요?

**A.** `enrichment.py`의 **회사명·이벤트 키워드**(실적, M&A, 규제, AI 등) 점수로 헤드라인을 랭킹한 뒤 상위부터 시도합니다. 투자 관련성이 높은 기사를 먼저 읽도록 설계했습니다.

### Q13. deep-read가 실패하는 대표 이유는?

**A.** (1) 페이월·봇 차단으로 본문 0자, (2) 타임아웃(`timeout_navigation_ms` 30초), (3) 동적 로딩 실패. 로그에 `Extracted article body was too short`로 남고, 성공한 건만 `news_enrichment.json`의 `deep_read_articles`에 쌓입니다. TSLA처럼 3건 중 2건만 성공하는 경우가 실제로 있습니다.

### Q14. FinBERT는 어디서 돌고, 입력은 무엇인가요?

**A.** `src/news/sentiment.py`의 `enrich_with_finbert_sentiment()`. 모델은 `ProsusAI/finbert`, Hugging Face `transformers` pipeline. 입력은 기사 **제목+요약**(최대 512자). 출력은 positive/negative/neutral 확률이며, UI 배지·요약 탭 종합 감성에 씁니다.

### Q15. FinBERT와 LLM 감성 분석을 둘 다 쓰나요?

**A.** 감성 **수치**는 FinBERT(로컬 추론, API 비용 없음). 리포트 **서술**은 LLM 에이전트가 context의 `news_summary`를 참고합니다. 역할을 나눠 비용·재현성을 맞췄습니다.

### Q16. Playwright MCP 없이도 돌아가나요?

**A.** deep-read 단계는 MCP 연결 실패 시 해당 기사만 스킵하고 파이프라인은 계속됩니다. Node.js·`npx`가 없으면 deep-read 성공 건수가 0에 가깝습니다. `brew install node` 필요.

---

## D. 2/5 피처·컨텍스트

### Q17. FeatureBuilder와 ContextBuilder 차이는?

**A.** `FeatureBuilder`(`src/features/builder.py`)가 snapshot에서 PER, 성장률, 기술적 지표(ATR, 지지선 등) 같은 **계산 피처**를 만듭니다. `ContextBuilder`(`src/report/composer.py`)가 snapshot·피처·뉴스 enrichment를 **LLM·에이전트가 읽기 좋은 JSON 스키마**로 합쳐 `context.json`을 씁니다.

### Q18. context 토큰 예산은 왜 체크하나요?

**A.** `ContextBuilder.check_token_budget()`가 tiktoken으로 추정 토큰을 재고, 모델 컨텍스트 한도를 넘지 않게 합니다. 로그에 `추정 토큰≈N (예산 내: True/False)`가 찍힙니다.

### Q19. 에이전트에게 context 전체를 한 번에 주지 않는 이유는?

**A.** `src/agents/context_slicer.py`의 `split_context()`가 valuation / financials / growth / risk **슬라이스**로 나눕니다. 각 도메인 에이전트는 자기 슬라이스만 보므로 환각·누락을 줄이고, 병렬 실행이 가능합니다.

---

## E. 3/5 LLM 리포트 (Agents)

### Q20. 에이전트는 몇 개이고 어떻게 협업하나요?

**A.** 일반 주식: **valuation, financials, growth, risk** 4개 도메인 에이전트가 `agents.parallel: true`이면 `asyncio.gather`로 **병렬** 실행 → 결과를 **composer_agent**가 6섹션 Markdown으로 합칩니다. ETF류는 holdings + risk → `etf_composer_agent` 분기(`orchestrator._is_etf_like`).

### Q21. yfinance MCP는 에이전트가 뭘 하나요?

**A.** `make_yfinance_server()`로 에이전트별 MCP 세션을 열어, 프롬프트만으로 부족한 **추가 시세·재무 조회**를 도구 호출로 보완합니다(`agents.tools_enabled`). MCP 초기화 실패 시 경고만 찍고 도구 없이 계속합니다.

### Q22. 리포트 6섹션 구조는 어떻게 강제하나요?

**A.** Composer 프롬프트 + 생성 후 `postcheck.validate_report_contract()`가 헤더 `### 1. 투자 요약` … `### 6. 투자 결론` 존재·본문 최소 길이·내부 필드명 노출(`price_technicals` 등)·PER 표기 등을 검사합니다. AAPL이 한때 실패한 `Final report is missing required header for section 2`가 여기서 난 **postcheck 오류**입니다.

### Q23. OpenAI Agents SDK를 쓴 이유는?

**A.** 단일 프롬프트 대비 **역할 분리·구조화 출력(Pydantic 스키마)·도구(MCP) 연동**이 SDK에 맞춰져 있어, 「재무 에이전트 / 리스크 에이전트」 데모 스토리와 맞습니다. `openai-agents==0.17.1` 고정.

### Q24. 어떤 모델을 쓰나요? 키는 어디에?

**A.** `config.yaml` → `llm.model` (예: `gpt-5.4-nano`), `base_url`은 Mindlogic 게이트웨이. API 키는 **환경변수** `OPENAI_API_KEY`만 (`.env` / `api_guide/.env`, 커밋 금지). `FINANCIAL_AI_MODEL` env로 런타임 오버라이드 가능.

### Q25. sections/ 폴더는 뭔가요?

**A.** agents 모드 실행 시 `artifacts/<티커>/<날짜>/sections/`에 `valuation.json`, `financials.json`, `composer_output.json` 등 **에이전트 중간 산출물**이 저장됩니다. 디버깅·발표 시 「에이전트가 뭘 냈는지」 보여줄 때 유용합니다.

---

## F. 4/5 평가 (M0 + M2)

### Q26. 규칙 채점(M0)은 무엇을 보나요?

**A.** `eval/rules.py`의 `run_all_checks()`: 출처 표기율(`[출처:…]`), 과도한 확신 표현 감점, 리스크 키워드 커버리지, 목표가·PER 일치 등 **정규식·키워드** 기반. ETF는 별도 루브릭 variant.

### Q27. LLM Judge(M2)는 언제 돌아가나요?

**A.** `config.yaml` `eval.use_llm_judge: true`이고 CLI에 `--no-judge`가 없을 때. `run_llm_judge()`가 6항목 서술 품질을 채점해 규칙 점수와 `aggregate()`로 합산합니다. API 실패 시 규칙만으로 fallback.

### Q28. eval.json의 점수는 리포트 품질만 보나요, 주가 예측 정확도인가요?

**A.** **리포트 품질·형식·리스크 서술** 루브릭입니다. `tracking/prediction_log.csv`에 3m/12m 사후 검증 컬럼이 있지만, 과제 범위에서는 **스텁·추적용**이며 자동 백테스트까지는 구현하지 않았습니다.

---

## G. 5/5 신호·트래킹

### Q29. signal.json은 어떻게 만들어지나요?

**A.** `trading_stub/signal.py`의 `extract_signal_from_report()`가 리포트 Markdown에서 매수/중립/매도 의견·신뢰도를 **규칙 기반 추출**합니다. 실제 주문·포지션 연동은 없는 **스텁**입니다.

### Q30. prediction_log.csv는 왜 쌓나요?

**A.** 날짜·티커·당시 가격·의견·목표가·루브릭 점수를 한 줄로 남겨, 나중에 사후 검증(방향 적중 등)을 **수동·배치**로 할 수 있게 하려는 설계입니다.

---

## H. 웹 대시보드·캐시

### Q31. 캐시 hit 조건은?

**A.** `web/cache.py`의 `is_complete_run()`: `snapshot.json`, `context.json`, `eval.json`, `signal.json` + `reports/<티커>/<날짜>.md`(80자 이상) + `run_manifest.json` status=complete. **FinBERT·community 완비 여부는 검사하지 않습니다.** 기능 업데이트 후에는 CLI 재실행 또는 「캐시 무시」가 필요합니다.

### Q32. 웹에서 분석 실행 시 백엔드 흐름은?

**A.** `POST /api/analyze` → `web/jobs.py`가 스레드에서 `run_for_dashboard()` 실행 → `GET /api/jobs/{job_id}`로 폴링 → 완료 후 `GET /api/runs/{ticker}/{date}`로 JSON 로드. 프론트는 `static/app.js`가 탭별 렌더링.

### Q33. 공개 URL 보안은?

**A.** `--public` 시 `DASHBOARD_API_TOKEN` 자동 생성, 분석·민감 API는 `?token=` 또는 헤더 필요. IP별 rate limit(`security.py`). 상세는 [SECURITY.md](SECURITY.md).

### Q34. 프론트 차트는 어떤 라이브러리?

**A.** **Lightweight Charts**(TradingView)로 `snapshot`의 OHLCV를 캔들로 그립니다. 목표가·손절은 리포트/context에서 파싱한 참고선입니다.

---

## I. 한계·정직한 답변 (꼬리질문 대비)

### Q35. 이 시스템이 실제 매매에 쓸 수 있나요?

**A.** **아니요.** 데모·교육용입니다. 데이터 지연, 단일 데이터원, LLM 환각, 신호 스텁, 사후 검증 미완을 전제로 합니다. 면책은 README·UI에 명시했습니다.

### Q36. LLM이 숫자를 지어낼 수 있지 않나요?

**A.** 가능합니다. 대응은 (1) context에 yfinance **실제 수치** 우선 주입, (2) 리포트 `[출처:…]` 요구, (3) postcheck·규칙 채점으로 PER/목표가 불일치 탐지, (4) Judge로 서술 품질 검사. **완전 방지는 불가**하므로 「보조 도구」로 포지셔닝합니다.

### Q37. 왜 RAG/벡터 DB는 안 썼나요?

**A.** 범위상 **당일 스냅샷 + 최근 뉴스 N건**이면 충분하고, 티커·날짜별 `artifacts/` JSON이 사실상 구조화된 컨텍스트 저장소 역할을 합니다. 장기 문서 검색이 필요하면 Chroma 등 확장 포인트로 남겼습니다.

### Q38. 테스트는 어떻게 검증했나요?

**A.** `pytest` — `tests/test_web_dashboard.py`, `test_web_security.py`, `test_news_sentiment.py` 등. LLM 출력 전체는 비결정적이라 **postcheck·규칙·API 계약** 위주로 자동화했습니다.

### Q39. 가장 자주 터지는 운영 이슈는?

**A.** (1) cloudflared URL 재시작 시 변경, (2) OPENAI_API_KEY 미설정, (3) deep-read/ community Yahoo 측 실패, (4) 구버전 캐시로 UI가 빈 감성·종토방. → [DEMO_GUIDE.md](DEMO_GUIDE.md) 트러블슈팅 참고.

### Q40. 다음에 확장한다면?

**A.** community Playwright 수집, 캐시 완료 조건에 `news_enrichment` 포함, 사후 가격 자동 채우기, Judge 기본 on/off 정책, 한국 뉴스 대체 소스. [ONBOARDING.md](ONBOARDING.md) 확장 포인트와 동일합니다.

---

## 발표 직후 5분 복습 체크리스트

- [ ] 5단계 파일명: `snapshot` → `context` → `report.md` → `eval` → `signal`
- [ ] agents = 4 도메인 + composer, legacy = 단일 호출
- [ ] deep-read = Playwright MCP, 감성 = FinBERT (로컬)
- [ ] postcheck = 6섹션 헤더 강제 (AAPL 실패 사례 설명 가능)
- [ ] 캐시 = 4 JSON + report, FinBERT/community 미포함
- [ ] 투자 권유 아님 + Yahoo 한계 정직히

---

## 관련 문서

| 문서 | 용도 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 다이어그램·모듈 맵 |
| [SOURCE_MAP.md](SOURCE_MAP.md) | 파일별 역할 |
| [FEATURES.md](FEATURES.md) | 기능 목록 |
| [SECURITY.md](SECURITY.md) | 공개 URL Q&A |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | 당일 체크리스트 |
