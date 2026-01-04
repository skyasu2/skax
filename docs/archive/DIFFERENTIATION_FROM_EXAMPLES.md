# PlanCraft vs 예제 코드 비교

본 문서는 일반적인 LangGraph 예제 코드와 PlanCraft 구현의 차이점을 정리한다.

---

## 1. 일반 예제 vs PlanCraft 비교

### 1.1 State 설계

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| State 정의 | 단순 TypedDict | 30+ 필드의 PlanCraftState |
| 불변성 | 직접 수정 | `update_state()` 헬퍼 사용 |
| Pydantic 호환 | 없음 | `ensure_dict()` 유틸 제공 |

```python
# 일반 예제
class State(TypedDict):
    messages: List[str]

state["messages"].append("new")  # 직접 수정

# PlanCraft
new_state = update_state(state, draft=new_draft)  # 불변성 보장
```

---

### 1.2 Multi-Agent 패턴

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| 에이전트 수 | 2~3개 | 10개 |
| 실행 방식 | 순차적 | DAG 기반 병렬 실행 |
| 라우팅 | LLM 매번 호출 | 결정론적 키워드 라우팅 |
| Registry | 하드코딩 | AGENT_REGISTRY 동적 로딩 |

```python
# 일반 예제 - LLM 기반 라우팅
def route(state):
    response = llm.invoke("어떤 에이전트?")  # 매번 LLM 호출
    return response.agent

# PlanCraft - 결정론적 라우팅
TECH_KEYWORDS = frozenset(["앱", "웹", "ai", "클라우드"])

def detect_required_agents(service: str) -> List[str]:
    agents = ["market", "bm", "risk"]  # 기본
    if any(kw in service.lower() for kw in TECH_KEYWORDS):
        agents.append("tech")  # 규칙 기반
    return agents
```

---

### 1.3 HITL (Human-in-the-Loop)

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| Interrupt 유형 | 1개 | 4가지 (option/confirm/form/approval) |
| Validation | 없음 | Strict/Lenient 모드 |
| Resume Schema | 자유 형식 | Pydantic 타입 정의 |

```python
# 일반 예제
def human_node(state):
    value = interrupt({"question": "계속?"})
    return {"answer": value}  # 검증 없음

# PlanCraft - Validation
class OptionResumeValue(BaseResumeValue):
    selected_option: Optional[Dict[str, Any]]

    @validator('selected_option')
    def validate_option(cls, v):
        if v and 'value' not in v:
            raise ValueError("option must have 'value' field")
        return v
```

---

### 1.4 RAG

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| 검색 방식 | 단순 similarity | MMR + Multi-Query |
| Reranker | 없음 | Cross-Encoder (선택적) |
| Context 배치 | 순서대로 | Long Context Reorder |

---

## 2. 구현 목록

| 기능 | 파일 | 설명 |
|:---|:---|:---|
| 결정론적 라우팅 | `agents/supervisor.py` | 키워드 기반 에이전트 선택 |
| AGENT_REGISTRY | `agents/agent_config.py` | 동적 에이전트 로딩 |
| 6개 Specialist | `agents/specialists/*.py` | 도메인별 전문 분석 |
| Validation | `graph/interrupt_types.py` | HITL 입력 검증 |
| Resume Schema | `graph/interrupt_types.py` | Pydantic 타입 안전 Resume |
| Cross-Encoder | `rag/reranker.py` | 검색 재정렬 (선택적) |
| Presets | `utils/settings.py` | fast/balanced/quality 모드 |

---

## 3. 코드 규모

```
일반 예제:     약 200 LOC
PlanCraft:    약 15,000+ LOC

테스트:
일반 예제:    약 10개
PlanCraft:    315개
```

---

## 4. 요약

| 항목 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| 에이전트 수 | 2~3개 | 10개 |
| 라우팅 방식 | LLM 기반 | 규칙 기반 |
| HITL 유형 | 1개 | 4개 |
| Validation | 없음 | Pydantic 기반 |
| 테스트 수 | ~10개 | 315개 |

---
