# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

> 참고: 본 레포의 1차 문서는 한국어입니다 — `README.md`(사용자 관점)와 `docs/ONBOARDING.md`(스켈레톤·확장 포인트)를 먼저 읽으세요. 본 파일은 그 위의 짧은 운영 메모입니다.

## 단일 진입점 (절대 규칙)

- 모든 실행은 **`scripts/run_pipeline.py`** 한 곳에서만 시작합니다. `python src/...` 형태로 모듈을 직접 호출하지 마세요 — 그렇게 돌릴 수 있게 설계돼 있지 않습니다.
- `run_pipeline.py`는 시작 시 `src/`를 `sys.path`에 삽입합니다. 따라서 **레포 안의 모든 임포트는 `from eval.judge import ...`, `from features.builder import ...` 형태이며 `src.` 접두사를 쓰지 않습니다.** 새 코드를 추가할 때도 이 규약을 따르세요.
- `fio/` 패키지는 표준 라이브러리 `io` 와의 충돌을 피하려고 일부러 이름을 바꾼 것입니다. 이름을 되돌리지 마세요.

## 자주 쓰는 명령

```bash
# 환경 — uv 가 .python-version(3.12) 기준으로 .venv 를 만들고 의존성을 설치합니다.
uv sync

# 단일 티커 end-to-end (LLM 호출 포함)
uv run scripts/run_pipeline.py --ticker AAPL

# 개발 중 빠른 검증 — LLM 없이 스텁 리포트로 나머지 단계만 점검
uv run scripts/run_pipeline.py --ticker AAPL --skip-llm

# 배치
uv run scripts/run_pipeline.py --tickers AAPL,MSFT,GOOG
uv run scripts/run_pipeline.py --tickers-file tickers.txt

# 게이트웨이에서 키로 접근 가능한 모델 목록 확인 (모델 ID 바꿀 때 필수)
uv run scripts/run_pipeline.py --list-models

# 이번 실행만 LLM Judge(M2) 강제 ON/OFF
uv run scripts/run_pipeline.py --ticker AAPL --judge
uv run scripts/run_pipeline.py --ticker AAPL --no-judge

# 의존성을 추가/제거할 때는 pip 가 아니라 uv 명령을 사용합니다.
uv add <패키지>
uv remove <패키지>
uv lock --upgrade-package <패키지>
```

테스트 프레임워크는 없습니다. 코드 변경 후 검증 루프는 **`--skip-llm` 으로 한 티커 돌려서 `artifacts/<TICKER>/<날짜>/{snapshot,context,eval,signal}.json` 가 생성되는지 확인** → LLM 경로가 영향받는 변경이면 키 있는 환경에서 LLM 모드로 한 번 더 돌리는 것입니다.

> 의존성·Python 버전의 단일 출처는 **`pyproject.toml`** + **`uv.lock`** 입니다. `requirements.txt` 는 더 이상 사용하지 않습니다 (제거됨). `uv.lock` 은 커밋 대상이며, `.venv/` 는 `.gitignore` 처리되어 있습니다.

## 데이터 흐름 (한눈)

```
yfinance → ingest/yahoo.py → snapshot.json
        → features/builder.py + report/composer.py → context.json
        → report/llm.py (Jinja `prompts/report.j2`) → reports/<티커>/<날짜>.md
        → eval/rules.py (M0 규칙)  ─┐
        → eval/judge.py (선택, M2) ─┴→ eval/rubric.aggregate → eval.json
        → trading_stub/signal.py → signal.json + tracking/prediction_log.csv 1행
```

각 단계는 `[pipeline] 1/5 …` 형태로 콘솔에 로그합니다. 배치는 `artifacts/_batch/<날짜>/batch_summary.json` 에 요약, 실패 시 `errors.json` 도 생깁니다.

## 평가 모드 — 헷갈리기 쉬운 부분

`eval.json` 의 `total_score` 의미가 **모드에 따라 다릅니다**. 채점 로직을 건드릴 때 반드시 두 모드를 모두 의식하세요.

- **M0 (`rubric_mode: "M0_rules_only"`)**: 규칙 엔진이 9개 루브릭 중 3개만 채점 (`source_transparency`+`risk_coverage`+`forecast_verifiability`, 합 상한 25) + 페널티. `total_score`는 **원점수(약 0~25 + 페널티)**, 등급은 `score_normalized_100` (25→100 스케일)에서 산정.
- **M2 (`rubric_mode: "M2_full"`)**: 위 3개 + LLM Judge 6개 항목(`eval/judge.py`). `total_score`가 **이미 100점 스케일** (+ 페널티).
- 활성화: `config.yaml: eval.use_llm_judge: true` 또는 CLI `--judge`. 끄려면 `--no-judge`.
- 규칙·Judge·페널티의 통합은 항상 `src/eval/rubric.py::aggregate` 를 거치게 두세요. 점수를 다른 곳에서 직접 합산하지 마세요.

## 설정·환경 변수

키 로드 순서(우선순위 높은 쪽이 이김):
1. 셸 환경 변수 (`OPENAI_API_KEY` 등)
2. `financial-ai/.env`
3. `financial-ai/api_guide/.env`

(파이썬 `load_dotenv` 기본 동작상 셸 환경 변수가 가장 강합니다.)

추가 오버라이드 환경 변수:
- `FINANCIAL_AI_MODEL` — `config.yaml: llm.model` 을 덮어씀.
- `FINANCIAL_AI_USER_AGENT` — Mindlogic 게이트웨이 WAF 통과용 UA. `report/llm.py` 에서 OpenAI SDK 요청과 모델 목록 조회 양쪽에 주입됩니다. 게이트웨이가 비브라우저 UA를 막을 때 가장 먼저 의심하세요 (`403`, `error code: 1010`).

`.env`/`api_guide/llm_credentials.txt` 등 키 파일은 `.gitignore` 됩니다 — 커밋에 끌려들어가지 않게 주의.

## 산출물 디렉터리 — 절대 커밋 금지

`artifacts/`, `reports/`, `tracking/`, `logs/` 는 실행 시 자동 생성되며 `.gitignore` 처리돼 있습니다. 파이프라인이 직접 만들도록 두고, 정리할 때는 디렉터리째 지워도 안전합니다. 날짜 폴더는 **UTC 기준** `YYYY-MM-DD` 입니다 (`report/composer.today_str`).

## 자주 마주치는 함정

- **한국 종목**은 `005930.KS` 처럼 `.KS` 접미사. 재무 필드가 비는 경우가 흔하니 새 피처를 추가할 때 `None` 가드를 두세요.
- **`permission_denied - No access to Model '…'`**: 키가 해당 모델 권한이 없는 것 — `--list-models` 결과 중에서 고르세요.
- **PER 불일치 페널티**: `eval/rules.py::_extract_reported_per` 가 "리포트 본문 PER" vs "원자료 PER" 을 대조해 차이가 2.0 이상이면 -5점. 리포트 템플릿이나 컨텍스트의 `valuation.PER` 형식을 바꾸면 이 규칙이 깨질 수 있으니 같이 손보세요.
- **토큰 예산**: `ContextBuilder.TOKEN_LIMIT = 5000` (gpt-4o 인코더 기준). 컨텍스트에 필드를 추가하면 `context.json._token_check.within_budget` 가 `False` 가 되는지 확인하세요.

## 변경 위치 빠른 매핑

`docs/ONBOARDING.md` §4–§5 에 모듈별 책임과 "이걸 바꾸려면 어디 보는지" 매핑이 있습니다. 새 기능을 추가하기 전에 그 표부터 확인하세요 — 보통 `src/` 와 `prompts/` 안에서 해결됩니다.
