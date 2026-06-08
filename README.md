# 금융 AI 리포트 파이프라인

> **투자 권유가 아닙니다.** 생성물은 참고용 데모이며, 실제 거래 전 반드시 원자료와 교차 검증하세요.

---

## 핵심 요약

| | |
|---|---|
| **무엇을 하나** | Yahoo Finance 데이터 수집 → 뉴스 심층 읽기 → **LLM 다중 에이전트** 투자 리포트 → 규칙·Judge 평가 → 매매 신호 스텁까지 **한 번에** 실행 |
| **CLI 진입점** | `scripts/run_pipeline.py` — 콘솔 `[pipeline] 1/5~5/5` |
| **웹 데모** | `scripts/run_dashboard.py` — 요약·리포트·뉴스·차트 탭, 공개 URL·캐시 지원 |
| **주요 산출물** | `reports/<티커>/<날짜>.md`, `artifacts/<티커>/<날짜>/`, `tracking/prediction_log.csv` |
| **기술 스택** | Python 3.12 · `uv` · yfinance · OpenAI Agents SDK · Playwright MCP · FastAPI |

**5단계 흐름**

```
수집·뉴스(1/5) → 컨텍스트(2/5) → LLM 리포트(3/5) → 평가(4/5) → 신호·CSV(5/5)
```

---

## 3분 빠른 시작

```bash
cd financial-ai
uv sync
# .env 또는 api_guide/.env 에 OPENAI_API_KEY=... 설정

uv run scripts/run_pipeline.py --ticker AAPL          # CLI 전체 파이프라인
uv run scripts/run_dashboard.py --public              # 웹 데모 + 공개 URL (cloudflared 필요)
```

- `src/`는 라이브러리입니다. `python src/...`로 직접 실행하지 않습니다.
- `uv` 미설치: [uv 설치 가이드](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`)
- 뉴스 deep-read: **Node.js + `npx`** 필요 (`brew install node`)

---

## 발표·데모 문서

팀 리드·발표 청중용 자료는 **`docs/`** 에 정리되어 있습니다.

| 문서 | 내용 |
|------|------|
| [docs/README.md](docs/README.md) | 발표 문서 인덱스 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 시스템 아키텍처·데이터 흐름 (mermaid) |
| [docs/FEATURES.md](docs/FEATURES.md) | 기능 목록 (에이전트·평가·대시보드·캐시 등) |
| [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | **발표 당일** 체크리스트·시연 포인트·트러블슈팅 |
| [docs/SOURCE_MAP.md](docs/SOURCE_MAP.md) | 소스코드 폴더·파일 역할 맵 |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | 개발자 온보딩 (코드 수정·확장 포인트) |

---

## 진입점

| 구분 | 경로 | 역할 |
|------|------|------|
| **메인** | `scripts/run_pipeline.py` | 수집 → 컨텍스트 → 리포트 → 평가 → 신호 오케스트레이션 |
| **웹 데모** | `scripts/run_dashboard.py` | 브라우저에서 티커 입력·Job 실행·탭별 결과 조회 |
| 보조 | `scripts/list_gateway_models.py` | LLM 모델 목록 조회 (`--list-models`와 동일) |
| 배포 | `scripts/deploy_local.sh` | macOS launchd 백그라운드 (`--public`) |

---

## 파이프라인 단계

| 단계 | 내용 | 산출물(주요) |
|------|------|----------------|
| **1/5** | yfinance 수집 + 뉴스 심층 읽기(Playwright MCP) | `snapshot.json`, `news/*.md`, `news_enrichment.json` |
| **2/5** | 피처·컨텍스트 조립 | `context.json` |
| **3/5** | LLM 리포트 (`agents` 기본 / `legacy`) | `reports/<티커>/<날짜>.md` |
| **4/5** | 규칙 평가(M0) + (선택) LLM Judge(M2) | `eval.json` |
| **5/5** | 신호 스텁·예측 로그 | `signal.json`, `prediction_log.csv` |

**평가 모드**: M0(규칙 3항목) / M2(전체 9항목 루브릭, `--judge`). 상세 점수 체계는 [docs/FEATURES.md](docs/FEATURES.md) 참고.

---

## 자주 쓰는 명령

```bash
uv run python -m pytest -q                              # 테스트
uv run scripts/run_pipeline.py --ticker AAPL
uv run scripts/run_pipeline.py --ticker 005930.KS       # 한국 종목
uv run scripts/run_pipeline.py --tickers AAPL,MSFT,GOOG # 배치
uv run scripts/run_pipeline.py --ticker AAPL --skip-llm # LLM 생략 (빠른 점검)
uv run scripts/run_pipeline.py --list-models            # 사용 가능 모델 목록
```

### 웹 대시보드

```bash
uv run scripts/run_dashboard.py              # http://127.0.0.1:8765/
uv run scripts/run_dashboard.py --public     # https://….trycloudflare.com (팀 공유)
uv run scripts/run_dashboard.py --lan        # 같은 Wi‑Fi/LAN
```

| UI | 설명 |
|----|------|
| **요약** | 투자 의견·핵심 지표·테시스·리스크 (리포트 파싱) |
| **리포트** | 섹션별 Markdown 카드 |
| **뉴스** | 심층 읽기 기사 카드 |
| **상세 데이터** | 가격 차트(3M/6M/12M) + 목표가·손절 참고선 + JSON 아코디언 |

- **캐시**: 동일 티커·날짜 완료 산출물이 있으면 재생성 없이 로드 (UI 「캐시 무시」로 강제 재실행)
- **공유 링크**: `#AAPL/2026-06-08` 해시 URL
- **접속 현황**: 사이드바에서 방문자 수 확인 (`/api/visitors`)

> **공개 URL 주의**: `trycloudflare.com` 링크는 **서버+터널이 켜져 있을 때만** 동작합니다. 재시작 시 URL이 바뀌며, Mac 절전·종료 시 **Error 1033** 이 납니다. 최신 URL은 `logs/dashboard.public_url` 참고. → [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)

### 옵션 요약

| 옵션 | 설명 |
|------|------|
| `--ticker` / `--tickers` / `--tickers-file` | 단일·배치 실행 |
| `--date YYYY-MM-DD` | 산출물 날짜 폴더 (기본: 오늘 UTC) |
| `--skip-llm` | LLM 리포트 생략 |
| `--judge` / `--no-judge` | Judge(M2) 강제 ON/OFF |
| `--list-models` | 모델 목록만 조회 후 종료 |

환경 변수: `FINANCIAL_AI_MODEL`, `FINANCIAL_AI_USER_AGENT`

---

## 설정 (`config.yaml`)

| 키 | 설명 |
|----|------|
| `llm.mode` | `agents`(기본) 또는 `legacy` |
| `llm.model` / `llm.base_url` | 게이트웨이 모델·URL |
| `llm.api_key_env` | 기본 `OPENAI_API_KEY` |
| `agents.*` | 병렬 실행, MCP, 토큰 예산 |
| `mcp.playwright` | 뉴스 deep-read (기본 `npx @playwright/mcp@latest`) |
| `mcp.yfinance` | Agents 보강용 yfinance MCP (`uvx`) |
| `eval.use_llm_judge` | M2 Judge 기본 ON/OFF |

**API 키**: `financial-ai/.env` 또는 `api_guide/.env`에 `OPENAI_API_KEY=...` (커밋 금지)

---

## 디렉터리 구조

```
financial-ai/
├── scripts/run_pipeline.py    # ★ CLI 진입점
├── scripts/run_dashboard.py   # ★ 웹 데모
├── config.yaml
├── docs/                      # 발표·아키텍처·데모 가이드
├── src/
│   ├── ingest/  news/  features/  report/
│   ├── agents/  eval/  trading_stub/
│   └── web/                   # FastAPI + static UI
├── artifacts/   reports/   tracking/   logs/   # 실행 시 생성
```

상세 파일 맵: [docs/SOURCE_MAP.md](docs/SOURCE_MAP.md)

---

## 문제 해결 (요약)

| 증상 | 대응 |
|------|------|
| `npx: command not found` | `brew install node`, `config.yaml`에 `npx` 절대 경로 |
| 뉴스 deep-read 실패 | `artifacts/.../news_enrichment.json`의 `failures[]` 확인. 파이프라인은 계속 진행 |
| `403` / `error code: 1010` | `FINANCIAL_AI_USER_AGENT` 조정 |
| `permission_denied` 모델 | `--list-models`로 허용 모델 확인 |
| 공개 URL Error 1033 | 대시보드·터널 재시작, `logs/dashboard.public_url` 최신 링크 공유 |
| npm `ENOTEMPTY` | `rm -rf .playwright-mcp/npm-cache` 후 재실행 |

전체 트러블슈팅: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) · [docs/ONBOARDING.md](docs/ONBOARDING.md)

---

## 변경 이력

최신 항목이 위입니다. 상세 커밋: [GitHub](https://github.com/Alex3463/financial-ai/commits/main)

### 2026-06-08

- **발표 문서**: `docs/` — 아키텍처·기능·데모 가이드·소스 맵
- **웹 UI 개선**: 요약·리포트·뉴스·상세 데이터 탭, Lightweight Charts 가격 차트, 접속 현황
- **README** 두괄식 정리

### 2026-05-12

- Playwright/yfinance MCP PATH 보강, postcheck 완화
- ETF 전용 리포트·평가 루브릭, 커뮤니티 감성 수집

### 2026-05-11

- `uv`/`pyproject.toml` 기준 의존성, OpenAI Agents SDK 다중 에이전트 파이프라인

### 2026-05-09

- 초기 공개: yfinance → LLM 리포트 → 평가 → 신호 스텁 단일 진입점

---

## 로드맵

- **M0** (현재): 규칙 기반 부분 자동 채점
- **M2**: LLM Judge로 전체 루브릭 (`--judge`, `eval.use_llm_judge`)

설계 문서: 상위 폴더 `project_blueprint.md`, `blue_print_overview.md`
