# Human-in-the-Loop (HITL) 실무 가이드

PlanCraft의 HITL 시스템은 LangGraph 공식 `interrupt()` 패턴을 기반으로 구현되었습니다.
이 문서는 Interrupt/Resume 흐름의 멱등성 보장과 실무 배포 시 주의사항을 다룹니다.

## 목차

1. [핵심 원칙](#핵심-원칙)
2. [Interrupt 전후 멱등성](#interrupt-전후-멱등성)
3. [Resume 시점 상태 복원](#resume-시점-상태-복원)
4. [상태 초기화 체크리스트](#상태-초기화-체크리스트)
5. [Subgraph Interrupt 안전성](#subgraph-interrupt-안전성)
6. [다중 Interrupt 순서 관리](#다중-interrupt-순서-관리)
7. [실무 배포 가이드](#실무-배포-가이드)
8. [코드 리뷰 체크리스트](#코드-리뷰-체크리스트)

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

## Subgraph Interrupt 안전성

### Subgraph에서 Interrupt 사용 시 주의사항

LangGraph에서 서브그래프 내 interrupt 발생 시, 부모 노드/서브그래프의 코드가 재실행될 수 있습니다.

```python
# ⚠️ 주의: Subgraph에서 interrupt 발생 시 재실행 위험

def parent_node(state: PlanCraftState):
    # ❌ 위험: 서브그래프가 interrupt되면 이 코드가 재실행됨
    increment_global_counter()  # 전역 카운터 증가!

    # 서브그래프 호출
    result = call_subgraph(state)  # 여기서 interrupt 발생 가능

    return result

# ✅ 안전한 패턴
def safe_parent_node(state: PlanCraftState):
    # 멱등성 체크: 이미 처리된 경우 스킵
    if state.get("subgraph_started"):
        result = call_subgraph(state)
        return result

    # 최초 진입 시에만 실행할 코드
    state = update_state(state, subgraph_started=True)
    result = call_subgraph(state)

    return result
```

### Subgraph 재진입 방지 패턴

```python
def create_subgraph_with_guard():
    """Subgraph 재진입 감지 및 방어"""

    def guarded_entry(state: PlanCraftState):
        entry_key = f"subgraph_{subgraph_id}_entered"

        if state.get(entry_key):
            # 이미 진입한 상태 - side-effect 스킵
            print(f"[GUARD] Subgraph re-entry detected, skipping side-effects")
            return state

        # 최초 진입 - 진입 플래그 설정
        return update_state(state, **{entry_key: True})

    return guarded_entry
```

### 테스트 권장사항

```python
# tests/test_subgraph_interrupt.py

def test_subgraph_interrupt_no_side_effect_duplication():
    """서브그래프 interrupt 시 side-effect 중복 실행 방지 테스트"""

    call_count = {"value": 0}

    def counting_node(state):
        call_count["value"] += 1
        return state

    # 서브그래프에서 interrupt 발생 시뮬레이션
    # ... (테스트 로직)

    # 검증: side-effect가 1회만 실행되었는지
    assert call_count["value"] == 1, "Side-effect가 중복 실행됨!"
```

---

## 다중 Interrupt 순서 관리

### 단일 노드 내 다중 Interrupt

한 노드에서 여러 번 interrupt를 호출할 경우, resume 값의 순서가 호출 순서와 일치해야 합니다.

```python
# ⚠️ 주의: 다중 interrupt 시 순서 불일치 위험

def multi_step_input_node(state: PlanCraftState):
    # 첫 번째 interrupt
    step1_response = interrupt({"step": 1, "question": "이름을 입력하세요"})

    # 두 번째 interrupt
    step2_response = interrupt({"step": 2, "question": "이메일을 입력하세요"})

    # Resume 시 step1_response, step2_response 순서대로 값이 전달됨
    # 만약 순서가 바뀌면 데이터 불일치 발생!

    return update_state(state,
        name=step1_response["value"],
        email=step2_response["value"]
    )
```

### 안전한 다중 Interrupt 패턴

```python
# ✅ 권장: 명시적 step 관리

def multi_step_with_explicit_tracking(state: PlanCraftState):
    current_step = state.get("input_step", 1)

    if current_step == 1:
        response = interrupt({
            "step": 1,
            "step_id": "name_input",  # 명시적 ID
            "question": "이름을 입력하세요"
        })
        return update_state(state,
            name=response["value"],
            input_step=2
        )

    elif current_step == 2:
        response = interrupt({
            "step": 2,
            "step_id": "email_input",
            "question": "이메일을 입력하세요"
        })
        return update_state(state,
            email=response["value"],
            input_step=3  # 완료
        )

    # 모든 입력 완료
    return state
```

### 복합 폼에서의 Interrupt

```python
# 여러 agent가 교대로 human input을 요구하는 경우
# 각 agent에 distinct한 pause node 사용 권장

def create_agent_pause_node(agent_id: str):
    """Agent별 고유한 pause node 생성"""

    def pause_node(state: PlanCraftState):
        payload = {
            "agent_id": agent_id,
            "node_ref": f"pause_{agent_id}",  # 고유 참조
            "interrupt_id": f"{agent_id}_{uuid4().hex[:8]}",
            # ...
        }

        response = interrupt(payload)
        return handle_response(state, response, agent_id)

    return pause_node

# 사용
analyzer_pause = create_agent_pause_node("analyzer")
writer_pause = create_agent_pause_node("writer")
```

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

## 코드 리뷰 체크리스트

### 신규 Interrupt 노드 추가 시 필수 확인사항

새로운 interrupt 노드나 subgraph를 추가할 때 아래 체크리스트를 확인하세요:

#### ⚠️ Side-Effect 체크 (가장 중요!)

```
□ interrupt() 호출 전에 DB 쓰기 코드가 없는가?
□ interrupt() 호출 전에 외부 API 호출이 없는가?
□ interrupt() 호출 전에 전역 변수 수정이 없는가?
□ interrupt() 호출 전에 카운터 증가가 없는가?
□ interrupt() 호출 전에 파일 쓰기가 없는가?
□ interrupt() 호출 전에 이메일/알림 발송이 없는가?
```

#### 멱등성 체크

```
□ 동일한 입력으로 여러 번 실행해도 결과가 같은가?
□ 이미 처리된 경우를 감지하는 guard 조건이 있는가?
□ Resume 시 재실행되어도 안전한가?
```

#### Payload 체크

```
□ interrupt_id가 고유하게 생성되는가?
□ node_ref가 명시되어 있는가?
□ Pydantic 스키마로 payload가 검증되는가?
□ 사용자에게 보여줄 question이 명확한가?
```

#### Subgraph 체크 (해당 시)

```
□ 부모 노드에서 subgraph 호출 전 side-effect가 없는가?
□ 재진입 방지 guard가 구현되어 있는가?
□ subgraph 내 interrupt가 부모에 영향을 주지 않는가?
```

#### 테스트 체크

```
□ 정상 Resume 테스트가 있는가?
□ 잘못된 입력에 대한 Validation 테스트가 있는가?
□ 타임아웃/취소 시나리오 테스트가 있는가?
□ 다중 Resume 시나리오 테스트가 있는가?
```

### PR 리뷰 시 경고 문구

신규 interrupt 관련 코드 리뷰 시 다음 경고를 확인하세요:

```python
# 🚨 HITL 코드 리뷰 경고 🚨
#
# 이 노드는 interrupt()를 사용합니다.
# 다음 사항을 반드시 확인하세요:
#
# 1. interrupt() 호출 전에 side-effect 코드가 없어야 합니다.
#    - DB 저장, 외부 API 호출, 전역 변수 수정 등 금지
#    - Resume 시 interrupt() 이전 코드가 재실행됩니다!
#
# 2. 모든 상태 변경은 interrupt() 이후에 수행하세요.
#
# 3. 멱등성을 보장하세요 - 여러 번 실행해도 결과가 같아야 합니다.
```

### 신규 개발자 온보딩 가이드

HITL 관련 코드를 처음 작성하는 개발자는 다음을 먼저 읽으세요:

1. **필수**: 이 문서의 "핵심 원칙" 섹션
2. **필수**: LangGraph 공식 [Human-in-the-Loop 가이드](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
3. **권장**: `graph/workflow.py`의 `option_pause_node` 참조 구현
4. **권장**: `tests/test_interrupt_safety.py` 테스트 코드 분석

### 문제 발생 시 디버깅 순서

1. **side-effect 중복 실행**: interrupt 전 코드 검토 → 멱등성 guard 추가
2. **resume 값 불일치**: interrupt_id 및 순서 검토 → 명시적 step 관리
3. **상태 불일치**: checkpoint 확인 → 상태 초기화 누락 검토
4. **무한 루프**: 최대 재시도 제한 확인 → fail-safe 로직 추가

---

## 참고 자료

- [LangGraph HITL 공식 문서](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
- [NodeInterrupt 패턴](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/dynamic_breakpoints/)
- [Checkpoint & Resume](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [Plan-and-Execute 패턴](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/plan-and-execute/)
- [Supervisor 구조](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/)
