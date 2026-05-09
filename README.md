# 금융 AI 리포트 파이프라인

Yahoo Finance(`yfinance`)로 주식 데이터를 모으고, LLM으로 Markdown 리포트를 생성한 뒤, 규칙 기반으로 요약 점수를 매기고 매매 신호 스텁까지 한 번에 실행하는 **소규모 엔드투엔드 파이프라인**입니다.

> 투자 권유가 아닙니다. 생성물은 참고용이며, 실제 거래 전 반드시 원자료와 교차 검증하세요.

---

## 팀 온보딩 · 단일 진입점

**전체 파이프라인의 유일한 실행 진입점은 `scripts/run_pipeline.py` 입니다.**  
`src/` 는 라이브러리 코드이며, 직접 `python src/...` 로 돌리지 않습니다.

| 구분 | 경로 | 역할 |
|------|------|------|
| **메인 진입점** | `scripts/run_pipeline.py` | 수집 → 리포트 → 평가 → 신호 → CSV까지 오케스트레이션 |
| 보조 | `scripts/list_gateway_models.py` | 사용 가능 LLM 모델 목록만 조회 (`run_pipeline.py --list-models` 와 동등 목적) |

스켈레톤·데이터 흐름·「무엇을 바꾸면 무엇이 바뀌는지」는 **[docs/ONBOARDING.md](docs/ONBOARDING.md)** 에 정리되어 있습니다. 새 팀원은 해당 문서를 먼저 읽는 것을 권장합니다.

---

## 한 줄 실행

```bash
cd financial-ai
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/run_pipeline.py --ticker AAPL
```

기본값으로 오늘 날짜(UTC) 폴더에 산출물이 생깁니다.

실행 중 콘솔에는 **`[pipeline]`** 접두사로 단계(1/5~5/5)·주요 분기(`--skip-llm` / LLM)·저장 경로 요약이 출력됩니다.

---

## 평가 점수·등급 (루브릭 / 100점 만점)

이 프로젝트의 평가는 청사진(`project_blueprint.md`)의 9항목 루브릭(총 100점)을 따릅니다.

- **M0 (rules-only)**: 규칙 엔진이 3항목만 채점합니다.
  - `source_transparency` (0–10), `risk_coverage` (0–10), `forecast_verifiability` (0–5) + 페널티(예: 데이터 불일치 -5)
  - 이 모드에서는 `eval.json`에 `rubric_mode: "M0_rules_only"` 로 기록됩니다.
  - `total_score`는 **원점수(대략 0~25 + 페널티)** 이고, `score_normalized_100`는 **25점 만점 기준으로 100점 환산**한 값입니다.
- **M2 (rules + LLM Judge)**: LLM Judge가 나머지 6항목을 채웁니다.
  - `data_accuracy`(0–20), `financial_quality`(0–15), `valuation_soundness`(0–20), `logic_consistency`(0–10), `bias_check`(0–5), `readability`(0–5)
  - `eval.use_llm_judge: true` 또는 실행 시 `--judge` 로 활성화됩니다.
  - 이 모드에서는 `rubric_mode: "M2_full"` 이고, `total_score`가 **100점 스케일(±페널티)** 로 직접 의미를 갖습니다.

콘솔과 `eval.json`의 `grade_note`가 “현재 어떤 모드로 등급을 냈는지”를 설명합니다.

---

## 파이프라인 단계

| 순서 | 내용 | 산출물 |
|------|------|--------|
| 1 | 가격·재무·뉴스·추천 수집 | `artifacts/<티커>/<날짜>/snapshot.json` |
| 2 | 피처·컨텍스트 구성 → LLM 리포트 | `reports/<티커>/<날짜>.md`, `context.json` |
| 3 | 규칙 기반 평가(M0) + (선택) LLM Judge(M2) | `artifacts/.../eval.json` |
| 4 | 신호 스텁·예측 로그 한 줄 | `artifacts/.../signal.json`, `tracking/prediction_log.csv` |

---

## 설정 (`config.yaml`)

- **`llm.model`**: 사용할 모델 ID (게이트웨이에서 실제 호출 가능한 이름이어야 함).
- **`llm.base_url`**: OpenAI 호환 Chat Completions 베이스 URL.
- **`llm.api_key_env`**: 기본 `OPENAI_API_KEY` (환경변수가 가장 우선).
- **키 설정(단일 방식)**: **오직 `.env`로만 설정**합니다. `financial-ai/.env` 또는 `financial-ai/api_guide/.env` 중 하나에 `OPENAI_API_KEY=...` 를 넣으세요.

모델은 키·계정에 따라 일부만 허용될 수 있습니다. 목록은 아래 명령으로 확인하세요.

---

## 자주 쓰는 명령

### 전체 파이프라인

```bash
python scripts/run_pipeline.py --ticker AAPL
python scripts/run_pipeline.py --ticker 005930.KS --date 2026-05-09
```

### 배치(여러 티커 한 번에)

```bash
# 쉼표 구분
python scripts/run_pipeline.py --tickers AAPL,MSFT,GOOG

# 공백 나열도 가능
python scripts/run_pipeline.py --ticker AAPL MSFT GOOG

# 파일 기반 (한 줄 1티커, # 주석 가능)
python scripts/run_pipeline.py --tickers-file tickers.txt
```

배치 결과는 `artifacts/_batch/<날짜>/batch_summary.json`에 요약 저장되며, 실패가 있으면 `errors.json`이 같이 생성됩니다.

### 사용 가능한 LLM 모델만 조회 (선택용)

```bash
python scripts/run_pipeline.py --list-models
# 또는
python scripts/list_gateway_models.py
```

결과는 콘솔에 출력되고, `logs/available_models_latest.txt` 및 날짜별 로그에 저장됩니다.

### 옵션 요약

| 옵션 | 설명 |
|------|------|
| `--ticker` | 단일 티커 (배치 모드와 동시 사용 불가) |
| `--tickers` | 쉼표 구분 다종목 배치: `AAPL,MSFT,GOOG` |
| `--tickers-file` | 파일 기반 배치 (한 줄 1티커, `#` 주석 가능) |
| `--date` | 아티팩트 폴더 날짜 `YYYY-MM-DD` (기본: 오늘 UTC) |
| `--skip-llm` | LLM 리포트 생성 생략(스텁). 평가·신호 파이프라인만 점검할 때 사용 |
| `--judge` | 이번 실행만 LLM Judge(M2) 강제 ON (config 무시) |
| `--no-judge` | 이번 실행만 Judge OFF (config의 `eval.use_llm_judge` 무시) |
| `--list-models` | 게이트웨이 모델 목록만 조회 후 종료 |
| `--model-log` | (선택) 실행 시작 시 모델 목록 조회·콘솔·`logs/` 저장 |

환경 변수 **`FINANCIAL_AI_MODEL`** 로 `config.yaml`의 모델을 덮어쓸 수 있습니다.
환경 변수 **`FINANCIAL_AI_USER_AGENT`** 로 게이트웨이 User-Agent를 조정할 수 있습니다.

---

## 디렉터리 구조 (요약)

```
financial-ai/
├── README.md
├── docs/
│   └── ONBOARDING.md    # 스켈레톤·확장 포인트 (팀 온보딩)
├── api_guide/           # .env 템플릿만 제공 (키 파일은 커밋 금지)
├── config.yaml
├── requirements.txt
├── prompts/
│   ├── report.j2
│   └── judge.j2
├── scripts/
│   ├── run_pipeline.py  # ★ 단일 진입점
│   └── list_gateway_models.py
├── src/
│   ├── ingest/yahoo.py
│   ├── features/builder.py
│   ├── report/composer.py
│   ├── report/llm.py
│   ├── eval/rules.py
│   ├── eval/rubric.py
│   ├── eval/judge.py
│   ├── trading_stub/signal.py
│   └── fio/storage.py   # 표준 라이브러리 io 와 이름 충돌 방지
├── artifacts/      # 실행 시 생성 (git 무시)
├── reports/
├── tracking/
└── logs/
```

자세한 책임 분리는 [docs/ONBOARDING.md](docs/ONBOARDING.md) §3~§5 참고.

---

## 문제 해결

- **`403` / `"error code: 1010"`**  
  일부 게이트웨이는 비브라우저 클라이언트를 차단합니다. 이 프로젝트의 `report/llm.py`는 OpenAI SDK 요청에 브라우저형 `User-Agent`를 넣습니다. 필요 시 **`FINANCIAL_AI_USER_AGENT`** 로 변경 가능합니다.

- **`permission_denied - No access to Model '…'`**  
  해당 키로 그 모델을 쓸 권한이 없습니다. `--list-models`로 노출되는 ID 중 하나로 바꾸거나 관리 콘솔에서 권한을 확인하세요.

- **한국 상장 종목**  
  `005930.KS` 형식을 사용합니다. 재무 필드가 비는 경우가 많습니다.

---

## 로드맵 (설계 문서 기준)

- **M0**: 현재 — 규칙만으로 부분 자동 채점.
- **M2**: LLM Judge로 나머지 루브릭 항목(6개) 자동 채점 (`eval.use_llm_judge`, `--judge`).

상세 설계는 저장소 상위의 `project_blueprint.md`, `blue_print_overview.md`를 참고하면 됩니다.
