# LangGraph Human Interrupt Best Practice

> 📅 최종 업데이트: 2025-12-29

---

## 📋 필수 요소 체크리스트

| 항목 | 코드 위치 | 상태 |
|------|-----------|------|
| **interrupt() 함수** | `graph/workflow.py:option_pause_node` | ✅ |
| **checkpointer** | `graph/workflow.py:compile_workflow` → `MemorySaver()` | ✅ |
| **Command(resume=...)** | `graph/workflow.py:run_plancraft` | ✅ |
| **thread_id 관리** | `config={"configurable": {"thread_id": ...}}` | ✅ |
| **Side effect 분리** | interrupt 전 비효과적 코드만 | ✅ |
| **TypedDict 상태 관리** | `graph/state.py:PlanCraftState` | ✅ |

---

## 🔧 구현 코드

### 1. interrupt() 함수 사용 (Pause)

```python
# graph/workflow.py

from langgraph.types import interrupt, Command

def option_pause_node(state: PlanCraftState) -> Command:
    """
    휴먼 인터럽트 노드 (LangGraph 공식 Best Practice)
    """
    # [BEFORE INTERRUPT] 비효과적 코드만 (side effect 없음)
    payload = create_option_interrupt(state)
    
    # [INTERRUPT] 실행 중단 - 사용자 응답 대기
    user_response = interrupt(payload)
    
    # [AFTER INTERRUPT] Resume 후 실행
    updated_state = handle_user_response(state, user_response)
    
    return Command(update=updated_state, goto="analyze")
```

### 2. checkpointer 설정

```python
# graph/workflow.py

from langgraph.checkpoint.memory import MemorySaver

def compile_workflow():
    checkpointer = MemorySaver()  # 또는 RedisSaver, PostgresSaver
    return workflow.compile(checkpointer=checkpointer)
```

### 3. Command로 Resume 처리

```python
# graph/workflow.py

from langgraph.types import Command

def run_plancraft(user_input, ..., resume_command=None):
    config = {"configurable": {"thread_id": thread_id}}
    
    if resume_command:
        # Resume 실행
        input_data = Command(resume=resume_command.get("resume"))
    else:
        # 일반 실행
        input_data = inputs
    
    final_state = app.invoke(input_data, config=config)
```

### 4. thread_id 관리

```python
# app.py (Streamlit)

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

# 실행 시 thread_id 전달
run_plancraft(user_input, thread_id=st.session_state.thread_id)
```

### 5. 인터럽트 상태 확인

```python
# graph/workflow.py

snapshot = app.get_state(config)

if snapshot.next and snapshot.tasks:
    if hasattr(snapshot.tasks[0], "interrupts") and snapshot.tasks[0].interrupts:
        interrupt_payload = snapshot.tasks[0].interrupts[0].value
```

---

## ⚠️ 주의사항

### Side Effect 분리

```python
def option_pause_node(state):
    # ❌ 금지: interrupt 전에 side effect
    # response = external_api.call()  # Resume 시 중복 호출!
    
    payload = create_payload(state)  # ✅ 순수 함수만
    
    user_response = interrupt(payload)  # Pause 지점
    
    # ✅ 허용: interrupt 후에 side effect
    save_to_database(user_response)
    
    return Command(...)
```

### Resume Index 관리

하나의 노드에 interrupt가 여러 개인 경우:

```python
def multi_interrupt_node(state):
    # 첫 번째 interrupt (index 0)
    response1 = interrupt({"step": 1})
    
    # 두 번째 interrupt (index 1)
    response2 = interrupt({"step": 2})
    
    # Resume 시 올바른 순서로 값 전달 필요
```

---

## 🧪 테스트 예시

```python
import uuid
from langgraph.types import Command

# 1. 초기 실행 (Pause까지)
config = {"configurable": {"thread_id": str(uuid.uuid4())}}
result = graph.invoke({"user_input": "테스트"}, config)

# 2. 상태 확인
snapshot = graph.get_state(config)
print(f"Next: {snapshot.next}")  # 다음 노드
print(f"Interrupts: {snapshot.tasks[0].interrupts}")  # 인터럽트 정보

# 3. Resume 실행
result = graph.invoke(Command(resume={"option": "A"}), config)
```

---

## 📊 현재 시스템 상태

| 항목 | 상태 |
|------|------|
| **Human Interrupt 코드** | ✅ Best Practice 준수 |
| **실제 사용 여부** | ⚠️ 현재 비활성화 (정책: 질문 금지) |
| **활성화 조건** | `need_more_info: true` 반환 시 |

> 📝 **참고**: 현재 설계에서는 Analyzer가 항상 `need_more_info: false`를 반환하므로 Human Interrupt가 발생하지 않습니다. 
> 모호한 입력은 `is_general_query: true`로 처리하여 친절한 안내 메시지를 반환합니다.

---

## 📚 관련 문서

- [LangGraph Human-in-the-loop 공식 문서](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/)
- [에이전트 설계](agent-design.md)
- [시스템 다이어그램](SYSTEM_DIAGRAM.md)
