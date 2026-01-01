# Human-in-the-Loop (HITL) 실무 가이드

PlanCraft의 HITL 시스템은 LangGraph 공식 `interrupt()` 패턴을 기반으로 구현되었습니다.
이 문서는 Interrupt/Resume 흐름의 멱등성 보장과 실무 배포 시 주의사항을 다룹니다.

## 목차

1. [핵심 원칙](#핵심-원칙)
2. [Interrupt 전후 멱등성](#interrupt-전후-멱등성)
3. [Resume 시점 상태 복원](#resume-시점-상태-복원)
4. [상태 초기화 체크리스트](#상태-초기화-체크리스트)
5. [실무 배포 가이드](#실무-배포-가이드)

---

## 핵심 원칙

### 1. Interrupt 전 순수 함수 원칙

```python
# ✅ 올바른 패턴: interrupt() 전에는 순수 계산만
def option_pause_node(state: PlanCraftState):
    # 1. 상태에서 데이터 읽기 (순수)
    options = state.get("options", [])
    question = state.get("option_question", "")

    # 2. 페이로드 생성 (순수)
    payload = OptionInterruptPayload(
        question=question,
        options=normalize_options(options)
    )

    # 3. interrupt 호출 (여기서 실행 중단)
    response = interrupt(payload.to_dict())

    # 4. Resume 후 처리 (상태 변경은 여기서만)
    return handle_user_response(state, response)
```

```python
# ❌ 잘못된 패턴: interrupt 전에 부작용 발생
def bad_pause_node(state: PlanCraftState):
    # 부작용: DB 저장, 외부 API 호출 등
    save_to_database(state)  # ❌ Resume 시 중복 실행됨!

    response = interrupt(payload)
    return handle_response(state, response)
```

### 2. 멱등성(Idempotency) 보장

**멱등성**: 동일한 입력에 대해 여러 번 실행해도 결과가 같아야 함

```python
# interrupt 전 코드는 여러 번 실행될 수 있음:
# - 사용자가 브라우저 새로고침
# - 네트워크 오류로 재시도
# - Resume 후 다시 같은 노드 진입

def idempotent_pause_node(state: PlanCraftState):
    # ✅ 이미 처리된 경우 스킵
    if state.get("last_resume_value"):
        return state  # 중복 실행 방지

    # ✅ 동일 입력 → 동일 페이로드
    payload = create_payload_from_state(state)

    response = interrupt(payload)
    return handle_response(state, response)
```

---

## Interrupt 전후 멱등성

### Interrupt 전 (순수 함수 영역)

| 허용 | 금지 |
|------|------|
| state에서 값 읽기 | DB/파일 쓰기 |
| 페이로드 객체 생성 | 외부 API 호출 |
| 로컬 계산/변환 | 전역 변수 수정 |
| 로깅 (읽기 전용) | 카운터 증가 |

### Interrupt 후 (Resume 영역)

```python
def handle_user_response(state: PlanCraftState, response: dict):
    """Resume 시점에서만 상태 변경"""

    # 1. 응답 검증
    if not validate_response(response):
        raise ValidationError("Invalid response")

    # 2. 상태 업데이트 (여기서만 부작용 허용)
    return update_state(state,
        selected_option=response.get("selected"),
        last_resume_value=response,
        last_pause_type=None,  # 초기화
    )
```

---

## Resume 시점 상태 복원

### Checkpoint 기반 복원

LangGraph는 `interrupt()` 시점에 자동으로 checkpoint를 생성합니다:

```python
# Resume 시 LangGraph가 자동으로:
# 1. 마지막 checkpoint 로드
# 2. interrupt() 다음 줄부터 실행 재개
# 3. response 값을 interrupt() 반환값으로 전달

response = interrupt(payload)  # ← Resume 시 여기서 response 받음
new_state = handle_response(state, response)
```

### 상태 일관성 보장

```python
def ensure_state_consistency(state: PlanCraftState) -> PlanCraftState:
    """Resume 후 상태 일관성 검증"""

    # 필수 필드 확인
    required = ["user_input", "thread_id"]
    for field in required:
        if not state.get(field):
            raise StateError(f"Missing required field: {field}")

    # 카운터 범위 검증
    if state.get("refine_count", 0) > MAX_REFINE_LOOPS:
        raise StateError("Refine count exceeded")

    return state
```

---

## 상태 초기화 체크리스트

### Resume 시 초기화해야 할 필드

```python
# graph/interrupt_utils.py

def reset_pause_state(state: PlanCraftState) -> dict:
    """Pause 관련 상태 초기화 (Resume 완료 후 호출)"""
    return {
        # Interrupt 메타데이터 초기화
        "last_interrupt": None,
        "last_pause_type": None,

        # 옵션 선택 관련 (다음 Pause를 위해)
        "options": [],
        "option_question": None,

        # 에러 상태 초기화
        "error": None,
        "error_category": None,
    }

# 사용 예시
def after_resume(state: PlanCraftState, response: dict):
    # 응답 처리
    new_state = process_response(state, response)

    # Pause 상태 초기화
    reset_fields = reset_pause_state(state)
    return update_state(new_state, **reset_fields)
```

### 초기화 대상 필드 목록

| 필드 | 초기화 값 | 설명 |
|------|----------|------|
| `last_interrupt` | `None` | 마지막 인터럽트 정보 |
| `last_pause_type` | `None` | pause 타입 (option/form/confirm) |
| `options` | `[]` | 선택지 목록 |
| `option_question` | `None` | 질문 텍스트 |
| `error` | `None` | 에러 메시지 |
| `error_category` | `None` | 에러 카테고리 |

### 유지해야 할 필드

| 필드 | 설명 |
|------|------|
| `last_resume_value` | 사용자 응답 (감사 추적용) |
| `last_human_event` | HITL 이벤트 전체 (디버깅용) |
| `step_history` | 실행 이력 (누적) |
| `refine_count` | 리파인 카운터 (누적) |

---

## 실무 배포 가이드

### 1. 동시성 처리

```python
# ❌ 위험: 여러 사용자가 동일 thread_id 사용
thread_id = "shared_thread"

# ✅ 안전: 사용자별 고유 thread_id
thread_id = f"user_{user_id}_{session_id}"
```

### 2. 타임아웃 설정

```python
class InterruptConfig:
    # Interrupt 최대 대기 시간 (초)
    INTERRUPT_TIMEOUT = 3600  # 1시간

    # 타임아웃 시 자동 처리
    TIMEOUT_ACTION = "cancel"  # or "default_option"
```

### 3. 에러 복구

```python
def safe_resume(graph, thread_id: str, response: dict):
    """안전한 Resume 처리"""
    try:
        result = graph.invoke(
            Command(resume=response),
            config={"configurable": {"thread_id": thread_id}}
        )
        return result
    except Exception as e:
        # 복구 시도
        if is_recoverable(e):
            return retry_resume(graph, thread_id, response)

        # 복구 불가 시 사용자에게 알림
        return create_error_response(e)
```

### 4. 모니터링

```python
# HITL 이벤트 로깅 (LangSmith 연동)
def log_hitl_event(event_type: str, payload: dict):
    logger.info(f"[HITL:{event_type}] {json.dumps(payload)}")

    # LangSmith에 메타데이터 추가
    if LANGSMITH_ENABLED:
        add_run_metadata({
            "hitl_event": event_type,
            "hitl_payload": payload,
            "timestamp": datetime.now().isoformat()
        })
```

---

## 디버깅 팁

### 1. Interrupt 상태 확인

```python
# 현재 interrupt 상태 조회
def get_interrupt_status(graph, thread_id: str):
    state = graph.get_state({"configurable": {"thread_id": thread_id}})

    return {
        "is_interrupted": len(state.tasks) > 0,
        "pending_tasks": [t.name for t in state.tasks],
        "last_interrupt": state.values.get("last_interrupt"),
    }
```

### 2. Resume 히스토리 추적

```python
# step_history에서 HITL 이벤트 필터링
def get_hitl_history(state: PlanCraftState):
    history = state.get("step_history", [])
    return [
        h for h in history
        if h.get("step", "").startswith("HITL:")
    ]
```

### 3. 상태 스냅샷 비교

```python
from utils.time_travel import TimeTravel

# 두 시점의 상태 비교
tt = TimeTravel(graph, thread_id)
diff = tt.compare_states(step1=5, step2=10)
print(diff)  # 변경된 필드만 출력
```

---

## 참고 자료

- [LangGraph HITL 공식 문서](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
- [NodeInterrupt 패턴](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/dynamic_breakpoints/)
- [Checkpoint & Resume](https://langchain-ai.github.io/langgraph/concepts/persistence/)
