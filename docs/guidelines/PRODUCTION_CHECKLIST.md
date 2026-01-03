# ✅ PlanCraft 실전 배포 체크리스트 (Internal)

본 문서는 `ARCHITECTURE_REVIEW.md`의 제안 사항을 바탕으로 작성된 실전 배포 전 필수 점검 항목입니다.

> 📅 최종 업데이트: 2025-01-03
> ✨ 신규 추가: Exponential Backoff with Jitter 구현 완료

## 1. 인프라 및 설정 (Infrastructure)

- [ ] **DB Checkpointer 전환**
  - [ ] `PostgresSaver` (추천) 또는 `RedisSaver` 의존성 추가 (`pip install psycopg-pool`)
  - [ ] `app.py` 또는 `workflow.py`에 DB 연결 문자열 환경 변수 처리
  - [ ] DB 스키마 초기화 스크립트 작성
- [ ] **환경 변수 검증**
  - [ ] `AOAI_API_KEY` 등 Secret 관리 (Key Vault 등 연동)
  - [ ] `LANGCHAIN_TRACING_V2=true` 확인 (프로덕션 모니터링)

## 2. 코드 및 로직 (Code Logic)

- [x] **Input Validation Loop 적용** ✅
  - [x] `option_pause_node`에 입력값 유효성 검사 로직 추가 (`interrupt_utils.py:387-399`)
- [x] **Error Handling 강화** ✅
  - [x] LLM API 타임아웃/RateLimit 발생 시 Backoff 재시도 로직 (아래 상세 참조)
  - [ ] 치명적 오류 발생 시 사용자에게 "죄송합니다" 메시지 및 관리자 알림(Sentry 등) 연동

### 2.1 Exponential Backoff with Jitter (신규 구현)

LLM API 호출 시 Rate Limit, 네트워크 오류에 대한 자동 재시도 기능이 구현되었습니다.

**구현 파일:**
- `utils/retry.py`: 중앙화된 Retry 유틸리티
- `utils/llm.py`: `get_llm_with_retry()` 함수 추가

**Best Practice 적용:**
| 항목 | 구현 내용 |
|:---|:---|
| **Retriable 예외 분류** | 5xx, 429, 네트워크 오류만 재시도 |
| **Non-Retriable 예외** | 4xx, 인증 오류는 즉시 실패 |
| **Exponential Backoff** | 1s → 2s → 4s (2배씩 증가) |
| **Jitter** | ±50% 랜덤 추가 (Thundering Herd 방지) |
| **최대 대기 시간** | 60초 |
| **최대 재시도 횟수** | 3회 (설정 가능) |

**사용법:**
```python
from utils.llm import get_llm_with_retry

# 프로덕션 권장
llm = get_llm_with_retry(temperature=0.7, max_retries=3)
response = llm.invoke(messages)

# Structured Output과 함께 사용
from utils.schemas import AnalysisResult
llm = get_llm_with_retry().with_structured_output(AnalysisResult)
```

**참조 문서:**
- [LangChain Rate Limiting Guide](https://docs.langchain.com/langsmith/rate-limiting)
- [RunnableRetry API](https://api.python.langchain.com/en/latest/runnables/langchain_core.runnables.retry.RunnableRetry.html)

## 3. 운영 및 모니터링 (Ops)

- [ ] **Logging Strategy**
  - [x] FileLogger 구현 (`utils/file_logger.py`)
  - [ ] 파일 로그 외에 ELK 스택 또는 CloudWatch 등으로 로그 전송 설정
- [ ] **Health Check**
  - [ ] `/health` 엔드포인트 생성 (Streamlit의 경우 별도 모니터링 포트 확인)

## 4. 확장성 (Scalability Test)

- [ ] **Load Testing**
  - [ ] locust 등을 사용하여 100+ 동시 세션 처리 시 Checkpointer 성능 확인
- [ ] **Recovery Testing**
  - [ ] 실행 도중 프로세스 강제 종료 후 재시작 시 상태 복구 여부 검증

---

## 구현 완료 항목 요약

| 항목 | 상태 | 구현 위치 |
|:---|:---:|:---|
| Checkpointer Factory | ✅ | `utils/checkpointer.py` |
| Input Validation | ✅ | `graph/interrupt_utils.py` |
| Error Categories | ✅ | `utils/error_handler.py` |
| **Exponential Backoff** | ✅ | `utils/retry.py`, `utils/llm.py` |
| FileLogger | ✅ | `utils/file_logger.py` |
| LangSmith Tracing | ✅ | `utils/tracing.py` |
