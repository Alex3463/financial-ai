# 기능 목록

발표·데모 관점에서 **사용자가 체감하는 기능**을 정리했습니다. 구현 위치는 괄호 안 경로를 참고하세요.

---

## 1. 엔드투엔드 파이프라인

**한 번의 명령으로** 데이터 수집부터 리포트·평가·신호까지 실행합니다.

- **진입점**: `scripts/run_pipeline.py`
- **5단계 진행 표시**: 콘솔 `[pipeline] 1/5 ~ 5/5`
- **단일 티커**: `uv run scripts/run_pipeline.py --ticker AAPL`
- **한국 종목**: `005930.KS` 형식
- **배치**: `--tickers AAPL,MSFT` 또는 `--tickers-file tickers.txt`
- **날짜 지정**: `--date 2026-06-08` → `artifacts/<티커>/<날짜>/` 폴더에 산출물 저장

### 산출물

| 파일 | 설명 |
|------|------|
| `artifacts/.../snapshot.json` | Yahoo Finance 원시 스냅샷 |
| `artifacts/.../context.json` | LLM·평가용 통합 컨텍스트 |
| `artifacts/.../eval.json` | 루브릭 점수·등급·플래그 |
| `artifacts/.../signal.json` | 매수/관망/매도 신호 스텁 |
| `reports/<티커>/<날짜>.md` | 최종 Markdown 투자 분석 리포트 |
| `tracking/prediction_log.csv` | 예측 이력 누적 (후속 검증용 필드 예약) |

---

## 2. 다중 에이전트 리포트 (Agents)

기본 모드(`config.yaml` → `llm.mode: agents`)에서 **OpenAI Agents SDK**로 도메인별 분석 후 합성합니다.

### 일반 주식

1. **컨텍스트 슬라이싱** (`agents/context_slicer.py`) — 밸류·재무·성장·리스크 블록 분리
2. **도메인 에이전트** (병렬 실행 가능)
   - Valuation — 밸류에이션·목표가 논리
   - Financials — 재무 현황
   - Growth — 성장 동력
   - Risk — 리스크 요인
3. **컴포저** (`composer_agent.py`) — 6섹션 Markdown 리포트 합성
4. **계약 검증** (`postcheck.py`) — 섹션·PER·산식·출처 형식 검사

### ETF / 펀드

- `holdings_agent` + `etf_composer_agent` 전용 경로
- Top Holdings, 보수, AUM, 섹터 비중 등 `funds_data` 활용
- ETF 전용 postcheck·평가 루브릭 분기
- **출처 정규화** (`agents/source_citations.py`): LLM이 `provided input`, `fund_operations.expense_ratio` 같은 내부 필드를 써도 저장 전 `Yahoo Finance ETF profile` 등 **엔드유저용 라벨**로 치환
- 데모 캐시 예: `SPY` / `2026-06-08`

### MCP 도구 보강

- **yfinance MCP** (`uvx yfmcp`): 에이전트가 실시간 도구 호출로 컨텍스트 보강 (실패 시 기존 `context.json`만으로 계속)
- 설정: `config.yaml` → `mcp.yfinance`

### Legacy 모드

- `llm.mode: legacy` 시 단일 LLM 호출 + `prompts/report.j2`
- 빠른 실험·비교용

### 스텁 모드

- `--skip-llm`: LLM 없이 내장 스텁 리포트 → 평가·신호 파이프라인만 검증 (데모·CI용)

---

## 3. 뉴스 심층 읽기 (News Deep-Read)

Yahoo Finance 뉴스 헤드라인만이 아니라 **기사 본문을 브라우저로 열어** 요약합니다.

- **모듈**: `src/news/enrichment.py`
- **MCP**: Playwright (`npx @playwright/mcp@latest`)
- **산출물**: `news/*.md`, `news_enrichment.json` (성공·실패·digest 메타)
- **실패 허용**: deep-read 실패해도 파이프라인은 계속 (실패 목록은 `failures[]`에 기록)
- **설정**: `ingest.news_count`, `mcp.playwright.*`

발표 포인트: 「뉴스 링크만이 아니라 실제 기사 내용을 읽고 리포트에 반영한다」

### FinBERT 뉴스 감성 (`src/news/sentiment.py`)

- **모델**: `ProsusAI/finbert` (Hugging Face `transformers`)
- **시점**: 1/5 뉴스 enrich 직후 → `news_enrichment.json`의 `sentiment_analysis`
- **점수**: `sentiment_score = positive − negative` (+1 긍정 ~ −1 부정)
- **웹**: 뉴스 탭 종합 히어로 + 기사별 배지·확률 바, 요약 탭 한 줄 표시
- **캐시 보강**: `POST /api/sentiment/{ticker}/{date}` (기존 산출물에 감성 없을 때)
- **설정**: `config.yaml` → `news.sentiment.enabled`, `FINANCIAL_AI_SKIP_SENTIMENT=1`로 생략

---

## 4. 평가 루브릭 (Eval)

청사진(`project_blueprint.md`)의 **9항목·100점 만점** 루브릭을 따릅니다.

### M0 — 규칙만 (`eval/rules.py`)

| 항목 | 만점 | 내용 |
|------|------|------|
| source_transparency | 10 | 출처·인용 비율 |
| risk_coverage | 10 | 리스크 키워드·커버리지 |
| forecast_verifiability | 5 | 목표가·기간 검증 가능성 |
| (+ 페널티) | — | 데이터 불일치 등 감점 |

`eval.json` → `rubric_mode: "M0_rules_only"`

### M2 — 규칙 + LLM Judge (`eval/judge.py`)

M0 항목 + Judge 6항목:

| 항목 | 만점 |
|------|------|
| data_accuracy | 20 |
| financial_quality | 15 |
| valuation_soundness | 20 |
| logic_consistency | 10 |
| bias_check | 5 |
| readability | 5 |

- 활성화: `eval.use_llm_judge: true` 또는 `--judge`
- `eval.json` → `rubric_mode: "M2_full"`, `total_score`가 100점 스케일

### ETF 전용 M0

비용 구조·포트폴리오 구성 등 ETF 맞춤 규칙 항목 (`eval/rubric.py` ETF 분기)

---

## 5. 매매 신호 스텁 (Trading Stub)

실제 주문이 아닌 **데모용 신호 JSON**입니다.

- **모듈**: `src/trading_stub/signal.py`
- 리포트 텍스트에서 투자 의견·목표가·신뢰도 추출
- **산출물**: `signal.json` (buy / hold / sell), `prediction_log.csv` 한 줄 append
- 후속 백테스트·트래킹(M3~) 확장을 위한 스키마 예약

---

## 6. 웹 대시보드 (탭형 데모 UI)

브라우저에서 티커 입력 → 파이프라인 실행 → 결과를 탭으로 확인합니다.

- **실행**: `uv run scripts/run_dashboard.py`
- **기본 URL**: `http://127.0.0.1:8765/`
- **구현**: `src/web/` (FastAPI + 정적 프론트)

### UI 탭 (5개)

| 탭 | 내용 | 파이프라인 대응 |
|----|------|-----------------|
| **요약** | 투자 의견·현재가·목표가·손절·핵심 근거·리스크 (ETF는 보수·AUM·상위보유 칩) | 3/5 리포트 + 4/5 평가 + 5/5 신호 요약 |
| **리포트** | 6섹션 구조화 렌더 (주식 KV 카드 / **ETF 전용** 보유표·리스크·전략표) | 3/5 Markdown 파싱 |
| **뉴스** | deep-read 기사 + **FinBERT 감성** 배지·확률 바·종합 감성 히어로 | 1/5 news_enrichment |
| **종토방** | Yahoo Finance community 게시판 UI·여론 요약·키워드 | 1/5 snapshot.community |
| **상세 데이터** | 주가 캔들 차트·평가 breakdown·원본 JSON | 1/5 snapshot + 2/5 context + 4/5 eval + 5/5 signal |

### 헤더

- **GitHub 배너** — [Alex3463/financial-ai](https://github.com/Alex3463/financial-ai) 링크
- 공개 URL 시 공유 박스 (`?token=` 포함)

### 사이드바 기능

- 티커·기준일 입력, 옵션 체크박스 (LLM 생략, Judge, 캐시 무시)
- **진행 로그** — `[pipeline]` 메시지 실시간 폴링
- **접속 현황** — 최근 5분 내 요청 IP (공개 URL 시 Cloudflare IP일 수 있음)
- **최근 실행** — `artifacts/` 이력에서 즉시 재로드

### URL 공유

- 결과 화면 주소가 `#AAPL/2026-06-08` 해시로 갱신 → 붙여넣기 공유 가능

---

## 7. 결과 캐시

같은 티커·날짜에 **완료된 산출물**이 있으면 재생성 없이 디스크에서 로드합니다.

- **판별**: `src/web/cache.py` → `is_complete_run()`  
  (`snapshot`, `context`, `eval`, `signal` + 리포트 80자 이상)
- **효과**: 공개 URL 데모 시 LLM 비용·대기 시간 절감
- **강제 재생성**: UI 「캐시 무시」 또는 API `force_refresh: true`
- **힌트**: 폼 입력 시 `/api/cache/{ticker}` 로 캐시 여부 표시

---

## 8. 공개 터널 (Public URL)

인터넷 어디서나 대시보드에 접속할 수 있습니다.

- **실행**: `uv run scripts/run_dashboard.py --public`
- **요구**: `brew install cloudflared`
- **URL**: `https://….trycloudflare.com` (재시작마다 변경)
- **기록**: `logs/dashboard.public_url`, 콘솔 출력, UI 헤더 「공개 링크」
- **LAN 모드**: `--lan` → `0.0.0.0` 바인드, 같은 Wi‑Fi 기기 접속

### launchd 백그라운드

`./scripts/deploy_local.sh` — Mac 재부팅 후에도 대시보드·터널 유지 (발표 장시간 데모용)

---

## 9. 주가 차트

**상세 데이터** 탭에서 TradingView **Lightweight Charts** 캔들 차트를 표시합니다.

- **데이터**: `snapshot.price.daily_close` 등 일봉 OHLCV
- **기간**: 3M / 6M / 12M 버튼
- **참고선**: 리포트·context에서 추출한 목표가·손절·컨센서스 수평선
- **구현**: `src/web/static/chart_view.js`

---

## 10. 방문자·접속 현황

공개 데모 시 「누가 보고 있는지」 근사적으로 표시합니다.

- **API**: `GET /api/visitors`
- **구현**: `src/web/access_log.py` — 최근 5분 내 요청 IP = 「접속 중」
- **주의**: Cloudflare 터널 경유 시 IP가 프록시 IP로 보일 수 있음

---

## 11. 기타 운영 기능

| 기능 | 설명 |
|------|------|
| **모델 목록 조회** | `--list-models` / `scripts/list_gateway_models.py` |
| **환경 변수 오버라이드** | `FINANCIAL_AI_MODEL`, `FINANCIAL_AI_USER_AGENT` |
| **단위 테스트** | `uv run python -m pytest -q` (`tests/`) |
| **커뮤니티 감성** | Yahoo community 댓글 베스트 에포트 수집 (차단 시 스킵) |

---

## 기능 ↔ 코드 빠른 참조

| 기능 | 핵심 경로 |
|------|-----------|
| 파이프라인 오케스트레이션 | `scripts/run_pipeline.py` |
| Yahoo 수집 | `src/ingest/yahoo.py` |
| 뉴스 deep-read | `src/news/enrichment.py` |
| 컨텍스트 조립 | `src/report/composer.py` |
| Agents 리포트 | `src/agents/orchestrator.py` |
| 평가 | `src/eval/rules.py`, `src/eval/judge.py` |
| 신호 | `src/trading_stub/signal.py` |
| 웹 API | `src/web/app.py` |
| 대시보드 실행 | `scripts/run_dashboard.py` |
