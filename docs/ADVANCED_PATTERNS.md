# PlanCraft Agent: 고급 패턴 가이드

> LangChain/LangGraph 공식 가이드 및 RAG 문서 추천 패턴 기반 코드 리뷰 및 실전 활용 가이드

---

## 1. 코드 베스트 프랙티스 (강점) 요약

### 1.1 SRP 기반 모듈화와 Pydantic State
- 각 `agents/` 기능 SRP 분리, Structured Output(Pydantic/JSON) 자동 검증 적용
- Immutable 상태 관리 (`model_copy`), cross-field validation, `step_history` 등
- 모든 입력/출력은 명확한 타입 주석과 docstring에 기반

### 1.2 LangGraph 공식 구조, Subgraph, 분기
- `StateGraph` / `subgraph` / `context-generation-qa` 3단계로 분할 (공식 튜토리얼 권장 구조)
- `conditional_edge`, human-interrupt 분기 정의
- `MemorySaver`로 타임트래블, 롤백, checkpoint, state diff 등 LangGraph 최신 기능 완비

### 1.3 LLM/RAG/Tool 사용 패턴 준수
- `with_structured_output(Pydantic)` → 실전 검증, 예외 fallback, validation, auto-correct
- 벡터 인덱스, RAG chunking, web search → tool node, fallback 등 적용

### 1.4 전체 파이프라인 Type-safe & Testable
- `tests/test_agents.py`로 각 단계별 타입 자동 검증
- UI도 SRP (`components`, `dialogs`, `refinement`) → 유지보수, 확장성 우수

---

## 2. LangChain & LangGraph 공식 How-to 관점 세부 권고

### 2.1 Structured Output, 스키마, with_structured_output

각 Agent의 LLM 출력에 `.with_structured_output(PydanticModel)` 적용 → **LangChain 권장 방식**

```python
# 현재 적용된 패턴 (이미 구현됨)
llm = get_llm().with_structured_output(AnalysisResult)
result = llm.invoke(messages)
```

**확장 옵션:**
- `include_raw=True`: 원본 출력과 파싱 결과 동시 반환
- Union 타입으로 복수 스키마 지원: `Union[OptionResponse, GeneralAnswer, PlanResult]`

### 2.2 분기/휴먼인터럽트: RunnableBranch, interrupt, Command

**현재 패턴:**
```python
# 조건부 edge 직접 구현
def should_ask_user(state):
    if state.need_more_info:
        return "ask_user"
    return "continue"

workflow.add_conditional_edges("analyze", should_ask_user, {...})
```

**권장 패턴 (RunnableBranch):**
```python
from langchain_core.runnables import RunnableBranch

branch = RunnableBranch(
    (lambda x: x["need_more_info"], ask_option_node),
    (lambda x: x["analysis"]["is_general_query"], general_response_node),
    default_main_flow
)
```

**휴먼 인터럽트 공식 패턴:**
```python
from langgraph.types import interrupt, Command

def option_pause_node(state):
    # 실행 중단 & UI로 질문/옵션/폼 전송
    resp = interrupt({"question": state.option_question, "options": state.options})
    # 사용자가 응답/옵션 선택하면 Command(resume=...)로 재시작
    return state.model_copy(update={"user_choice": resp})
```

### 2.3 상태모델의 jsonschema 활용, 폼 자동화 연동

모든 state/output schema는 Pydantic → jsonschema 변환:

```python
from graph.state import PlanCraftState

# JSON Schema 추출
schema = PlanCraftState.model_json_schema()

# 프론트엔드에서 react-jsonschema-form으로 자동 폼 생성
```

**활용처:**
- Dynamic form 자동 생성
- 옵션 안내 UI
- Validation 자동화
- 시나리오 분석/테스팅

### 2.4 타임트래블, 롤백, 브랜치 UI

```python
# 현재 구현됨
from graph.workflow import app as workflow_app

config = {"configurable": {"thread_id": session_id}}
history = list(workflow_app.get_state_history(config))

# 특정 시점으로 롤백
workflow_app.update_state(
    checkpoint_config,
    checkpoint_values,
    as_node=next_step
)
```

---

## 3. 실전 업그레이드 액션 아이디어

### 3.1 프론트 롤백/이력/분기 버튼 추가
- ✅ 이미 구현됨: Dev Tools > State History 탭

### 3.2 휴먼인터럽트/옵션선택 자동화
- 조건부분기/옵션선택 상태에서 자동 `interrupt` → UI 옵션/폼 → Command로 재실행
- jsonschema 활용해 자동폼 생성, 테스트 자동화

### 3.3 폼/입출력 자동화, 테스트 자동화
- 모든 state/output schema를 jsonschema로 추출
- `react-jsonschema-form`에 연결 → 입력폼, 출력 폼, 자동 검증

### 3.4 Agent 분기 복잡화/확장 시 RunnableBranch 적용
- 선택지/옵션 여러 개, 복잡 분기 조건 시 `RunnableBranch`로 단순화
- `ToolNode`/`BindableNode`로 LLM-Tool 연계 강화

### 3.5 서브그래프/병렬/부분재빌드 강화
- 각 subgraph를 별도 배포, 테스트, 병렬화 가능
- 마이크로서비스, 엔드포인트 분산에 준비됨

---

## 4. 구체적 코드 개선 제안

### 4.1 RunnableBranch 적용 예시

```python
from langchain_core.runnables import RunnableBranch

main_flow = RunnableBranch(
    (lambda x: x.need_more_info, option_pause_node),
    (lambda x: x.analysis.is_general_query, general_message_node),
    main_workflow_node
)
```

### 4.2 휴먼 인터럽트 공식 패턴

```python
from langgraph.types import interrupt, Command

def option_pause_node(state):
    resp = interrupt({
        "question": state.option_question, 
        "options": state.options
    })
    return state.model_copy(update={"user_choice": resp})
```

### 4.3 State/Pydantic 모델 스키마 활용

```python
# Dev Tools에서 이미 구현됨
from graph.state import PlanCraftState

schema = PlanCraftState.model_json_schema()
# → UI 폼 자동 생성에 바로 연결
```

---

## 5. 평가 요약

| 항목 | 점수 | 비고 |
|------|------|------|
| SRP 모듈화 | ⭐⭐⭐⭐⭐ | 완벽한 분리 |
| Pydantic Structured Output | ⭐⭐⭐⭐⭐ | 공식 권장 패턴 |
| LangGraph 구조 | ⭐⭐⭐⭐⭐ | 공식 튜토리얼 90% 일치 |
| 타임트래블/롤백 | ⭐⭐⭐⭐⭐ | 완전 구현 |
| 휴먼 인터럽트 | ⭐⭐⭐⭐☆ | 개선 여지 (interrupt() 패턴) |
| 폼 자동화 | ⭐⭐⭐⭐☆ | 스키마 노출됨, 폼 연동 가능 |
| 테스트 커버리지 | ⭐⭐⭐⭐☆ | 단위 테스트 존재, 통합 테스트 확장 권장 |

**종합: 현업/제품 환경 또는 대규모 챗봇/생성AI 파이프라인에도 손색없는 구조**

---

## 6. 참고 자료

- [LangChain: How to get models to return structured output](https://python.langchain.com/docs/how_to/structured_output/)
- [LangGraph: Quickstart](https://langchain-ai.github.io/langgraph/tutorials/quickstart/)
- [LangGraph: How to define input/output schema](https://langchain-ai.github.io/langgraph/how-tos/input_output_schema/)
- [LangGraph: Human-in-the-loop](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/)

---

*Last Updated: 2025-12-28*
