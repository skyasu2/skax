# PlanCraft HITL (Human-in-the-Loop) 개발자 가이드

> **⚠️ 필독!** 이 문서는 LangGraph interrupt() 메커니즘을 사용할 때 반드시 숙지해야 할 내용입니다.

## 📌 핵심 규칙

### 1. Interrupt 전 Side-Effect 금지

**가장 중요한 규칙입니다!**

```python
def my_node(state):
    # ❌ 잘못된 예 - interrupt 전에 Side-effect
    save_to_database(state)      # DB 저장
    send_email(state["user"])    # 이메일 발송
    external_api_call()          # 외부 API 호출
    
    value = interrupt(payload)   # 여기서 중단
    
    # Resume 시 → 이 노드가 처음부터 다시 실행됨!
    # → save_to_database, send_email이 또 실행됨! (중복 발생)
```

```python
def my_node(state):
    # ✅ 올바른 예 - interrupt 후에만 Side-effect
    payload = create_payload(state)  # 순수 함수, Side-effect 없음
    
    value = interrupt(payload)  # 여기서 중단
    
    # Resume 시 → 여기부터 실행
    save_to_database(state)      # 한 번만 실행됨
    send_email(state["user"])    # 한 번만 실행됨
    return result
```

---

### 2. SubGraph 내부 Interrupt 주의 ⚠️⚠️⚠️

**SubGraph 내부에서 `interrupt()` 사용 시 Resume 동작:**

```
┌─────────────────────────────────────────────────────────────────┐
│ Parent Graph                                                     │
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │   Node A     │───▶│   Node B     │───▶│   Node C     │      │
│   │              │    │ (SubGraph)   │    │              │      │
│   └──────────────┘    └──────┬───────┘    └──────────────┘      │
│                              │                                   │
│                              ▼                                   │
│                     ┌────────────────┐                           │
│                     │   SubGraph     │                           │
│                     │                │                           │
│                     │  ┌─────────┐   │                           │
│                     │  │ Sub-A   │   │                           │
│                     │  └────┬────┘   │                           │
│                     │       ▼        │                           │
│                     │  ┌─────────┐   │                           │
│                     │  │ Sub-B   │   │  ← interrupt() 발생!      │
│                     │  └─────────┘   │                           │
│                     │                │                           │
│                     └────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘

Resume 시 실행 순서:
1. Parent의 Node B (SubGraph 호출 노드)가 처음부터 재실행
2. SubGraph의 Sub-A가 처음부터 재실행
3. SubGraph의 Sub-B가 처음부터 재실행
4. interrupt()에서 값 반환되어 계속 진행
```

**결론:** 
- SubGraph 내 모든 노드의 interrupt 전 코드가 다시 실행됨
- 부모 노드의 interrupt 전 코드도 다시 실행됨
- **멱등성(Idempotency)** 보장 필수!

---

### 3. 멱등성 보장 패턴

```python
def safe_node(state):
    # ✅ 멱등한 코드 - 여러 번 실행해도 결과 동일
    payload = {
        "question": "옵션을 선택하세요",
        "options": get_options_from_state(state),
    }
    
    # ✅ 순수 함수 - Side-effect 없음
    formatted = format_payload(payload)
    
    # Interrupt
    value = interrupt(formatted)
    
    # ❗ Resume 이후에만 실제 작업 수행
    return process_user_input(state, value)
```

---

### 4. 다중 Interrupt 처리

하나의 노드에서 여러 interrupt가 있을 경우:

```python
def multi_interrupt_node(state):
    # 첫 번째 interrupt - index=0
    value1 = interrupt({"question": "첫 번째 질문"})
    
    # 두 번째 interrupt - index=1
    value2 = interrupt({"question": "두 번째 질문"})
    
    # 세 번째 interrupt - index=2
    value3 = interrupt({"question": "세 번째 질문"})
    
    return process(value1, value2, value3)
```

**Resume 순서:**
1. 첫 Resume → `value1`에 값 설정, 두 번째에서 다시 중단
2. 두 번째 Resume → `value2`에 값 설정, 세 번째에서 다시 중단
3. 세 번째 Resume → `value3`에 값 설정, 노드 완료

**주의:** 조건문으로 interrupt 위치가 바뀌면 index 매칭 오류 발생!

```python
def bad_pattern(state):
    # ❌ 위험한 패턴 - 조건에 따라 interrupt 순서 변경
    if state.get("need_extra"):
        extra = interrupt({"question": "추가 정보"})  # 때로는 index=0
    
    main = interrupt({"question": "메인 질문"})  # 때로는 index=0 또는 1
    
    # Resume 시 index 불일치 가능!
```

---

## 📋 페이로드 표준 필드

모든 interrupt 페이로드에 포함되어야 하는 필드:

| 필드 | 필수 | 설명 |
|------|------|------|
| `event_id` | ✅ | UUID, 이벤트 고유 식별자 |
| `node_ref` | ✅ | 발생 노드 이름 |
| `timestamp` | ✅ | ISO 8601 시각 |
| `type` | ✅ | 인터럽트 타입 |
| `question` | ✅ | 사용자 표시 메시지 |
| `options` | ❌ | 선택지 목록 |
| `error` | ❌ | 에러 메시지 (재시도 시) |
| `retry_count` | ❌ | 현재 재시도 횟수 |

**사용 예시:**
```python
from graph.hitl_config import create_option_payload

payload = create_option_payload(
    question="목차를 선택하세요",
    options=[
        {"title": "옵션 A", "description": "설명 A"},
        {"title": "옵션 B", "description": "설명 B"},
    ],
    node_ref="structure_approval"
)
```

---

## 🔧 확장 패턴

새 인터럽트 타입 추가:

```python
from graph.hitl_config import InterruptFactory, create_base_payload, InterruptType

# 1. 핸들러 함수 정의
def file_upload_handler(question, node_ref, **kwargs):
    return create_base_payload(
        InterruptType.FILE_UPLOAD,
        question, 
        node_ref,
        allowed_types=kwargs.get("allowed_types", [".pdf", ".docx"]),
        max_size_mb=kwargs.get("max_size_mb", 10),
    )

# 2. 팩토리에 등록
InterruptFactory.register("file_upload", file_upload_handler)

# 3. 사용
payload = InterruptFactory.create(
    "file_upload",
    question="파일을 업로드하세요",
    node_ref="file_input_node",
    allowed_types=[".csv", ".xlsx"],
    max_size_mb=5
)
```

---

## 📚 참고 자료

- [LangGraph HITL Guide](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/)
- [LangGraph SubGraph Docs](https://langchain-ai.github.io/langgraph/concepts/subgraphs/)
- `graph/hitl_config.py` - 설정 및 유틸리티
- `graph/interrupt_utils.py` - 응답 처리
- `graph/interrupt_types.py` - 타입 정의

---

## ✅ 체크리스트

새 노드에 interrupt 추가 시:

- [ ] interrupt 전 Side-effect 없음 확인
- [ ] 멱등한 코드만 interrupt 전에 배치
- [ ] 표준 페이로드 필드 포함
- [ ] SubGraph인 경우 부모 노드 영향 확인
- [ ] 다중 interrupt 시 순서 고정
- [ ] 테스트 케이스 작성

---

*마지막 업데이트: 2026-01-01*
