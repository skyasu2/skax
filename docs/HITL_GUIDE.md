# LangGraph Human-in-the-Loop (HITL) Implementation Guide

## 1. 개요
PlanCraft는 LangGraph의 `interrupt` / `Command` 패턴을 사용하여 강력하고 유연한 HITL(Human-in-the-Loop) 워크플로우를 구현합니다. 본 문서는 팀내 개발자가 안전하고 확장 가능한 형태로 인간 개입 로직을 추가/수정하는 방법을 가이드합니다.

## 2. Core Best Practices 🛡️

### 2.1 Side-Effect 배치 원칙 (매우 중요)
LangGraph의 `interrupt` 함수는 실행 상태를 중단(Suspend)시킵니다. 사용자가 입력을 제공하여 재개(Resume)할 때, **인터럽트가 발생한 노드는 처음부터 재실행**됩니다.

따라서, **Side-Effect(DB 저장, API 호출, LLM 생성 등) 코드는 반드시 `interrupt` 호출 이후에 배치**해야 합니다.

**❌ 잘못된 예시 (BAD):**
```python
def bad_node(state):
    # Resume 시 이 API 호출이 중복 발생함!
    result = api.call_expensive_service() 
    
    response = interrupt("계속하시겠습니까?")
    return Command(update={"data": result})
```

**✅ 올바른 예시 (GOOD):**
```python
def good_node(state):
    # 1. Payload 생성 (순수 연산)
    payload = {"question": "계속하시겠습니까?"}
    
    # 2. 실행 중단 (여기서 멈춤)
    response = interrupt(payload)
    
    # 3. Resume 후 실행 (Side-Effect 안전)
    # Resume 시에는 interrupt가 즉시 값을 반환하고 여기부터 실행됨
    result = api.call_expensive_service() 
    
    return Command(update={"data": result})
```

<br/>

### 2.2 Semantic Interrupt ID 사용
Multi-turn 대화나 복잡한 흐름에서 Resume 시점의 정합성을 보장하기 위해 `interrupt_id`를 명시적으로 사용하는 것을 권장합니다.

```python
payload = create_option_interrupt(state, interrupt_id="analyze_direction_select")
```
이를 통해 워크플로우 구조 변경 등으로 인해 노드 순서가 바뀌더라도, 올바른 인터럽트 지점을 식별할 수 있습니다.

## 3. 구현 패턴 (Patterns)

### 3.1 단순 승인 (Approval)
가장 기본적인 패턴으로, 다음 단계 진행 여부만을 묻습니다.
`make_approval_pause_node` 팩토리 함수를 사용하여 쉽게 생성할 수 있습니다.

### 3.2 옵션 선택 (Option Selection)
사용자에게 여러 선택지를 제공하고 분기 처리합니다. `agents/supervisor.py`의 라우팅과 결합하여 동적으로 경로를 변경할 수 있습니다.

### 3.3 다중 승인 체인 (Multi-Approval Chain)
Team Lead -> PO -> CTO 순서로 승인이 필요한 경우, `make_multi_approval_chain` 유틸리티를 사용합니다.

```python
approval_nodes = make_multi_approval_chain(
    approvers=[
        {"role": "Team Lead", "question": "팀장 승인"},
        {"role": "PO", "question": "PO 승인"}
    ],
    final_goto="deploy"
)
```

### 3.4 Multiple Interrupt (연쇄 질문)
사용자의 답변에 따라 즉시 추가 정보를 물어야 하는 경우(예: '기타' 선택 시 세부 내용 입력), `Command(goto='자기자신')`을 반환하여 노드를 재귀적으로 호출합니다.

```python
# graph/workflow.py 참조
if selected_opt == "기타":
    updated_state = update_state(..., need_more_info=True)
    return Command(update=updated_state, goto="option_pause") # 자기 자신 재호출
```

## 4. 체크포인터 활용 가이드 (Checkpointer)

### 4.1 체크포인터란?
LangGraph 체크포인터는 워크플로우 상태를 영속화하여 `interrupt` 후에도 정확한 지점에서 재개(Resume)할 수 있게 합니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Checkpointer 동작 흐름                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   [Node A] ──▶ [Node B] ──▶ interrupt() ──▶ 💾 State 저장               │
│                                    │                                     │
│                                    ▼                                     │
│                              사용자 대기                                  │
│                                    │                                     │
│                                    ▼                                     │
│                           graph.invoke(input,                            │
│                              config={thread_id})                         │
│                                    │                                     │
│                                    ▼                                     │
│                         💾 State 복원 ──▶ [Node B 재개] ──▶ [Node C]     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 체크포인터 종류

| 종류 | 용도 | 특징 |
|------|------|------|
| `MemorySaver` | 개발/테스트 | 메모리 기반, 프로세스 종료 시 데이터 손실 |
| `SQLiteSaver` | 로컬 배포 | 파일 기반 영속화, 간단한 설정 |
| `PostgresSaver` | 프로덕션 | 고가용성, 멀티 인스턴스 지원 |

### 4.3 체크포인터 설정 방법

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.postgres import PostgresSaver

# 1. 개발 환경 (메모리)
checkpointer = MemorySaver()

# 2. 로컬 환경 (SQLite)
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

# 3. 프로덕션 환경 (PostgreSQL)
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/plancraft"
)

# 그래프에 체크포인터 연결
graph = workflow.compile(checkpointer=checkpointer)
```

### 4.4 Thread ID 관리

체크포인터는 `thread_id`로 세션을 구분합니다. 동일한 `thread_id`로 호출하면 이전 상태에서 이어서 진행합니다.

```python
# 새 세션 시작
config = {"configurable": {"thread_id": "session_001"}}
result = graph.invoke({"user_input": "AI 앱 기획"}, config)

# 동일 세션 Resume (interrupt 응답)
result = graph.invoke(
    Command(resume={"selected_option": "웹 앱"}),
    config  # 동일한 thread_id 사용
)
```

### 4.5 상태 조회 및 Time-Travel

체크포인터를 통해 과거 상태를 조회하거나, 특정 시점으로 돌아갈 수 있습니다.

```python
# 현재 상태 조회
state = graph.get_state(config)
print(state.values)  # 현재 State dict
print(state.next)    # 다음 실행될 노드

# 상태 히스토리 조회
for state in graph.get_state_history(config):
    print(f"Step: {state.metadata.get('step')}")
    print(f"Checkpoint ID: {state.config['configurable']['checkpoint_id']}")

# 특정 체크포인트로 롤백
past_config = {
    "configurable": {
        "thread_id": "session_001",
        "checkpoint_id": "checkpoint_abc123"
    }
}
result = graph.invoke(Command(resume=new_input), past_config)
```

### 4.6 외부 시스템 상태 주의사항

> ⚠️ **중요**: LangGraph 체크포인터는 **워크플로우 State만** 복원합니다.
> 외부 시스템(DB, Redis, 3rd-party API) 상태는 복원되지 않습니다.

외부 시스템과 연동 시, interrupt 전에 해당 상태를 State에 저장하세요:

```python
def payment_node(state):
    # ❌ 위험: 외부 상태가 State에 없음
    # payment_id = external_api.create_payment()
    # response = interrupt("결제를 승인하시겠습니까?")

    # ✅ 안전: 외부 상태를 State에 저장
    payment_id = external_api.create_payment()

    # interrupt 전에 State에 저장
    state_update = {"pending_payment_id": payment_id}
    response = interrupt({
        "question": "결제를 승인하시겠습니까?",
        "snapshot": state_update  # 디버깅용 스냅샷
    })

    # Resume 후 State에서 복원
    return Command(update={
        **state_update,
        "payment_confirmed": response.get("confirmed")
    })
```

### 4.7 프로덕션 체크리스트

- [ ] `MemorySaver` 대신 `PostgresSaver` 또는 `SqliteSaver` 사용
- [ ] `thread_id` 생성 로직 구현 (UUID, 사용자 ID 조합 등)
- [ ] 오래된 체크포인트 정리 스케줄러 설정
- [ ] 체크포인트 데이터 백업 정책 수립
- [ ] Resume 실패 시 재시도 로직 구현

## 5. 트러블슈팅

- **Resume 후 무한 루프**: `interrupt` 함수가 값을 반환하지 않거나(None), 조건문 로직 오류일 수 있습니다. 입력 유효성 검사 로직(`while` 루프 등)을 확인하세요.
- **데이터 유실**: `Command` 객체의 `update` 필드에 누락된 상태값이 없는지 확인하세요. 부분 업데이트(`patch`) 방식이므로 필요한 값만 넘기면 덮어씌워지지 않고 병합됩니다.
- **Resume Mismatch**: `interrupt_id`가 일치하지 않으면 잘못된 interrupt에 응답할 수 있습니다. Semantic ID를 사용하고, 응답 전에 ID를 검증하세요.
- **체크포인트 누락**: `thread_id`가 다르면 새 세션으로 시작됩니다. 동일한 세션을 이어가려면 반드시 같은 `thread_id`를 사용하세요.

---
*Last Updated: 2025-01-03*
