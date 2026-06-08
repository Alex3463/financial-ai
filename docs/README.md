# 발표·데모 문서 (Financial AI)

팀 리드·발표 청중을 위한 **프로젝트 개요·아키텍처·기능·데모 가이드**입니다.  
개발자 온보딩(코드 수정·확장 포인트)은 별도 문서 **[ONBOARDING.md](ONBOARDING.md)** 를 참고하세요.

---

## 문서 목록

| 문서 | 대상 | 내용 |
|------|------|------|
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | 발표·기술 Q&A | 시스템 구조, 5단계 파이프라인, 모듈 맵, 웹 대시보드 아키텍처 |
| **[FEATURES.md](FEATURES.md)** | 발표·기능 소개 | 사용자 관점 기능 목록 (에이전트, 뉴스, 평가, 대시보드, 캐시 등) |
| **[DEMO_GUIDE.md](DEMO_GUIDE.md)** | 발표 당일 | 체크리스트, CLI·대시보드 실행, 탭별 시연 포인트, 트러블슈팅 |
| **[SOURCE_MAP.md](SOURCE_MAP.md)** | 「소스코드 구성」 질문 | 디렉터리 트리와 주요 파일 역할 |
| **[SECURITY.md](SECURITY.md)** | 웹 공개·보안 Q&A | 위험 목록, 토큰·속도 제한, 운영 권장 |

---

## 한 줄 요약

**Yahoo Finance 수집 → 뉴스 심층 읽기 → FinBERT 감성 → LLM 다중 에이전트 리포트 → 규칙·Judge 평가 → 매매 신호 스텁**까지 한 번에 돌리는 엔드투엔드 파이프라인입니다.  
실행 진입점은 `scripts/run_pipeline.py`, 브라우저 데모는 `scripts/run_dashboard.py` 입니다.

> 투자 권유가 아닙니다. 생성물은 참고용 데모입니다.

---

## 빠른 링크

- 프로젝트 루트 README: [../README.md](../README.md)
- 개발자 온보딩: [ONBOARDING.md](ONBOARDING.md)
- 설정: [../config.yaml](../config.yaml)
- 메인 진입점: [../scripts/run_pipeline.py](../scripts/run_pipeline.py)
- 웹 대시보드: [../scripts/run_dashboard.py](../scripts/run_dashboard.py)
- GitHub: [github.com/Alex3463/financial-ai](https://github.com/Alex3463/financial-ai)
