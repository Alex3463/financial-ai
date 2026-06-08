# 금융 AI 리포트 파이프라인

[![GitHub](https://img.shields.io/badge/GitHub-Alex3463%2Ffinancial--ai-181717?logo=github)](https://github.com/Alex3463/financial-ai)

> **투자 권유가 아닙니다.** 생성물은 참고용 데모이며, 실제 거래 전 반드시 원자료와 교차 검증하세요.

---

## 핵심 요약

| | |
|---|---|
| **무엇을 하나** | Yahoo Finance 수집 → 뉴스 심층 읽기 → **FinBERT 감성** → **LLM 다중 에이전트** 리포트 → 규칙·Judge 평가 → 매매 신호 스텁 |
| **CLI 진입점** | `scripts/run_pipeline.py` — 콘솔 `[pipeline] 1/5~5/5` |
| **웹 데모** | `scripts/run_dashboard.py` — 5탭 UI(종토방 포함), 주식·**ETF(SPY)** 전용 레이아웃, 공개 URL·캐시·API 토큰 |
| **저장소** | [github.com/Alex3463/financial-ai](https://github.com/Alex3463/financial-ai) |
| **기술 스택** | Python 3.12 · uv · yfinance · FinBERT · OpenAI Agents · Playwright MCP · FastAPI |

**5단계 흐름**

```
수집·뉴스·감성(1/5) → 컨텍스트(2/5) → LLM 리포트(3/5) → 평가(4/5) → 신호·CSV(5/5)
```

---

## 3분 빠른 시작

```bash
cd financial-ai
uv sync
# .env 또는 api_guide/.env 에 OPENAI_API_KEY=... 설정

uv run scripts/run_pipeline.py --ticker AAPL
uv run scripts/run_dashboard.py --public   # cloudflared 필요, ?token= URL 공유
```

- `src/`는 라이브러리 — `python src/...`로 직접 실행하지 않습니다.
- 뉴스 deep-read: **Node.js + npx** (`brew install node`)
- FinBERT: `transformers` + `torch` (첫 실행 시 모델 다운로드)

---

## 발표·데모 문서

| 문서 | 내용 |
|------|------|
| [docs/README.md](docs/README.md) | 발표 문서 인덱스 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 아키텍처·데이터 흐름 |
| [docs/FEATURES.md](docs/FEATURES.md) | 기능 목록 |
| [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | **발표 당일** 체크리스트 |
| [docs/SECURITY.md](docs/SECURITY.md) | 웹 공개·토큰·속도 제한 |
| [docs/TECH_QA_PREP.md](docs/TECH_QA_PREP.md) | **발표 후 기술 Q&A** (질문·답 40선) |
| [docs/SOURCE_MAP.md](docs/SOURCE_MAP.md) | 소스코드 맵 |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | 개발자 온보딩 |

---

## 진입점

| 구분 | 경로 | 역할 |
|------|------|------|
| **CLI** | `scripts/run_pipeline.py` | 전체 파이프라인 오케스트레이션 |
| **웹** | `scripts/run_dashboard.py` | 브라우저 데모 (FastAPI + static) |
| 배포 | `scripts/deploy_local.sh` | macOS launchd (`--public`) |

---

## 파이프라인 단계

| 단계 | 내용 | 산출물(주요) |
|------|------|----------------|
| **1/5** | yfinance + 뉴스 deep-read(최대 5건) + **FinBERT 감성** + Yahoo community | `snapshot.json`, `news_enrichment.json` |
| **2/5** | 피처·컨텍스트 | `context.json` |
| **3/5** | LLM 리포트 (`agents` / `legacy`) | `reports/<티커>/<날짜>.md` |
| **4/5** | 규칙(M0) + Judge(M2) | `eval.json` |
| **5/5** | 신호 스텁 | `signal.json`, `prediction_log.csv` |

---

## 웹 대시보드

```bash
uv run scripts/run_dashboard.py              # http://127.0.0.1:8765/
uv run scripts/run_dashboard.py --public     # 토큰 포함 공개 URL
```

| 탭 | 설명 |
|----|------|
| **요약** | 투자 의견·지표·FinBERT 감성·종토방 여론 힌트 |
| **리포트** | 섹션별 Markdown 카드 |
| **뉴스** | deep-read 기사 + FinBERT 배지·확률 바 (최대 10건) |
| **종토방** | Yahoo Finance community 게시판·여론 요약 |
| **상세 데이터** | Lightweight Charts + 참고선 + JSON |

### 발표용 캐시 일괄 생성

```bash
uv run scripts/run_pipeline.py \
  --tickers "AAPL,TSLA,NVDA,005930.KS,000660.KS,011070.KS" \
  --date $(date -u +%Y-%m-%d) --no-judge
```

기능 업데이트 후에는 **「캐시 무시」** 없이 재실행해야 FinBERT·5건 deep-read·community가 반영됩니다.

- 상단 **GitHub 배너** → [Alex3463/financial-ai](https://github.com/Alex3463/financial-ai)
- **캐시** · **접속 현황** · `#티커/날짜` 공유 URL
- **공개 모드**: API 토큰 자동 생성 → `?token=` 포함 URL 공유 ([SECURITY.md](docs/SECURITY.md))

---

## 설정 (`config.yaml`)

| 키 | 설명 |
|----|------|
| `llm.mode` | `agents`(기본) / `legacy` |
| `news.max_deep_reads` | 뉴스 deep-read 최대 건수 (기본 5) |
| `news.sentiment.enabled` | FinBERT 감성 (기본 true) |
| `mcp.playwright` | 뉴스 deep-read |
| `eval.use_llm_judge` | M2 Judge |

**API 키**: `.env` 또는 `api_guide/.env`에 `OPENAI_API_KEY` (커밋 금지)

---

## 디렉터리 구조

```
financial-ai/
├── scripts/run_pipeline.py
├── scripts/run_dashboard.py
├── src/news/sentiment.py      # FinBERT
├── src/web/security.py        # 공개 URL 보안
├── docs/
└── artifacts/  reports/  logs/
```

---

## 문제 해결 (요약)

| 증상 | 대응 |
|------|------|
| FinBERT 느림 | 첫 실행 모델 로딩 — 이후 캐시 |
| `npx` 없음 | `brew install node` |
| Error 1033 | 대시보드·터널 재시작 |
| 분석 401 | `?token=` 포함 URL 사용 |

→ [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) · [docs/SECURITY.md](docs/SECURITY.md)

---

## 변경 이력

[GitHub 커밋](https://github.com/Alex3463/financial-ai/commits/main)

### 2026-06-08 (최종)

- **FinBERT 뉴스 감성** + deep-read 5건 + 요약/뉴스 탭 UI
- **종토방 탭**: Yahoo community 게시판·여론 요약 (`/api/community`)
- **웹 보안**: API 토큰·속도 제한 ([docs/SECURITY.md](docs/SECURITY.md))
- 발표용 6티커 캐시 배치·`docs/` 문서·GitHub 배너

### 2026-05-12 · 2026-05-11 · 2026-05-09

- ETF 리포트, Agents SDK, 초기 파이프라인 공개

---

## 로드맵

- **M0**: 규칙 기반 채점 (현재)
- **M2**: LLM Judge 전체 루브릭 (`--judge`)
