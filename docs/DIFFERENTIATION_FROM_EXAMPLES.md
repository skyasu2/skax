# PlanCraft 차별화 포인트 (예제 코드 vs 실제 구현)

> **목적**: 강의 예제 코드와 PlanCraft 구현의 차이점을 명시하여 독자적인 설계임을 증명

---

## 1. 일반적인 LangGraph 예제 vs PlanCraft

### 1.1 State 설계

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| **State 정의** | 단순 `TypedDict` | 30+ 필드의 `PlanCraftState` |
| **불변성** | 직접 수정 | `update_state()` 헬퍼로 안전한 갱신 |
| **Pydantic 호환** | 없음 | `ensure_dict()` 유틸로 Pydantic↔Dict 변환 |

```python
# 일반 예제
class State(TypedDict):
    messages: List[str]

state["messages"].append("new")  # 직접 수정 (위험)

# PlanCraft 구현 (graph/state.py)
class PlanCraftState(TypedDict):
    user_input: str
    analysis: Optional[Dict]
    structure: Optional[Dict]
    specialist_results: Dict[str, Any]
    draft: Optional[str]
    final_plan: Optional[str]
    review: Optional[Dict]
    # ... 30+ 필드

new_state = update_state(state, draft=new_draft)  # 불변성 보장
```

---

### 1.2 Multi-Agent 패턴

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| **에이전트 수** | 2~3개 | **10개** (Supervisor + 6 Specialists + 3 Core) |
| **실행 방식** | 순차적 | **DAG 기반 병렬 실행** |
| **라우팅** | LLM 매번 호출 | **결정론적 키워드 라우팅** (LLM 최소화) |
| **Registry** | 하드코딩 | **AGENT_REGISTRY 동적 로딩** |

```python
# 일반 예제 - LLM 기반 라우팅
def route(state):
    response = llm.invoke("어떤 에이전트?")  # 매번 LLM 호출 (느림, 비용)
    return response.agent

# PlanCraft - 결정론적 라우팅 (agents/supervisor.py)
TECH_KEYWORDS = frozenset(["앱", "웹", "ai", "클라우드", ...])

def detect_required_agents(service: str, purpose: str) -> RoutingDecision:
    agents = ["market", "bm", "financial", "risk"]  # 기본

    if any(kw in service.lower() for kw in TECH_KEYWORDS):
        agents.append("tech")  # 규칙 기반 (빠름, 무비용)

    return RoutingDecision(required_analyses=agents, ...)
```

---

### 1.3 HITL (Human-in-the-Loop)

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| **Interrupt 유형** | 1개 (단순 confirm) | **4가지** (option/confirm/form/approval) |
| **Validation** | 없음 | **Strict/Lenient 모드** |
| **Resume Schema** | 자유 형식 | **Pydantic 타입 안전** |
| **시각화** | 없음 | **Mermaid Timeline/Sequence** |

```python
# 일반 예제
def human_node(state):
    value = interrupt({"question": "계속?"})
    return {"answer": value}  # 검증 없음

# PlanCraft - Strict Validation (graph/interrupt_types.py)
class ValidationMode(str, Enum):
    STRICT = "strict"    # 실패 시 예외 발생
    LENIENT = "lenient"  # 경고 후 진행

class OptionResumeValue(BaseResumeValue):
    selected_option: Optional[Dict[str, Any]]
    text_input: Optional[str]

    @validator('selected_option')
    def validate_option(cls, v):
        if v and 'value' not in v:
            raise ValueError("option must have 'value' field")
        return v
```

---

### 1.4 Specialist Agent (독자 설계)

**일반 예제에는 없는 PlanCraft 고유 기능:**

```python
# agents/specialists/market_agent.py - 도메인 특화 스키마
class MarketAnalysis(BaseModel):
    tam: MarketSize       # 전체 시장 (구조화된 스키마)
    sam: MarketSize       # 접근 가능 시장
    som: MarketSize       # 획득 가능 시장
    competitors: List[Competitor]  # 경쟁사 (최소 3개 강제)
    trends: List[str]
    opportunities: List[str]

class MarketAgent:
    def run(self, service_overview: str, target_market: str) -> MarketAnalysis:
        # 도메인 전문 프롬프트 + Pydantic 출력 검증
        llm = get_llm().with_structured_output(MarketAnalysis)
        return llm.invoke(prompt)
```

---

### 1.5 RAG 고급 기능

| 구분 | 일반 예제 | PlanCraft |
|:---|:---|:---|
| **검색 방식** | 단순 similarity | **MMR + Multi-Query + Reranking** |
| **Reranker** | 없음 | **Cross-Encoder (ms-marco-MiniLM)** |
| **Query 변환** | 없음 | **Query Expansion + 약어 확장** |
| **Context 배치** | 순서대로 | **Long Context Reorder** |

```python
# 일반 예제
docs = vectorstore.similarity_search(query, k=3)

# PlanCraft - 고급 검색 파이프라인 (rag/retriever.py)
retriever = Retriever(
    k=3,
    use_reranker=True,       # Cross-Encoder 재정렬
    use_multi_query=True,    # 변형 쿼리 생성
    use_query_expansion=True, # 약어/동의어 확장
    use_context_reorder=True  # Lost-in-the-Middle 해결
)
docs = retriever.get_relevant_documents(query)
```

---

## 2. PlanCraft 독자 구현 목록

| 기능 | 파일 | 설명 |
|:---|:---|:---|
| **결정론적 라우팅** | `agents/supervisor.py` | 키워드 기반 에이전트 선택 |
| **AGENT_REGISTRY** | `agents/agent_config.py` | 동적 에이전트 로딩 |
| **6개 Specialist** | `agents/specialists/*.py` | 도메인별 전문 분석 |
| **Strict Validation** | `graph/interrupt_types.py` | HITL 입력 검증 |
| **Resume Schema** | `graph/interrupt_types.py` | Pydantic 타입 안전 Resume |
| **Chain Visualization** | `graph/interrupt_types.py` | Mermaid 다이어그램 생성 |
| **Cross-Encoder Reranking** | `rag/reranker.py` | 검색 정확도 향상 |
| **Time Travel** | `utils/time_travel.py` | 상태 복원/재실행 |
| **Exponential Backoff** | `utils/retry.py` | LLM API 재시도 |
| **Generation Presets** | `utils/settings.py` | fast/balanced/quality 모드 |

---

## 3. 코드 라인 수 비교

```
일반 LangGraph 예제:     ~200 LOC
PlanCraft 구현:          28,969 LOC (145배)

테스트:
일반 예제:               ~10개
PlanCraft:               315개 (31배)
```

---

## 4. 아키텍처 다이어그램 (독자 설계)

```
┌─────────────────────────────────────────────────────────────────┐
│                         PlanCraft Agent                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌──────────────┐    ┌─────────────────────────┐│
│  │Streamlit│───▶│  LangGraph   │───▶│     Specialist Pool     ││
│  │   UI    │    │  StateGraph  │    │  ┌───┐┌───┐┌───┐┌───┐  ││
│  └─────────┘    └──────────────┘    │  │Mkt││BM ││Fin││Rsk│  ││
│       │                │            │  └───┘└───┘└───┘└───┘  ││
│       │         ┌──────┴──────┐     │  ┌───┐┌───┐            ││
│       │         │ HITL        │     │  │Tec││Cnt│ (조건부)   ││
│       └────────▶│ 4-type      │     │  └───┘└───┘            ││
│                 │ Interrupt   │     └─────────────────────────┘│
│                 └─────────────┘                                 │
│                        │                                        │
│  ┌─────────────────────┴─────────────────────────────────────┐ │
│  │                    Advanced RAG                            │ │
│  │  Multi-Query → Cross-Encoder Rerank → Context Reorder     │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. 결론

> **PlanCraft는 강의 예제의 "확장"이 아니라 "재설계"입니다.**

- 예제: 개념 증명 수준 (~200 LOC)
- PlanCraft: 프로덕션 레디 수준 (28,969 LOC)

### 핵심 차별점 요약

1. **10개 에이전트** 협업 (예제는 2~3개)
2. **결정론적 라우팅**으로 LLM 비용 절감
3. **4가지 HITL 유형** + Strict Validation
4. **Cross-Encoder Reranking** RAG
5. **315개 테스트**로 품질 보장
6. **Pydantic 스키마** 전면 적용
