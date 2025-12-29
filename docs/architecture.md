# PlanCraft Agent - 시스템 아키텍처

## 1. 시스템 개요

PlanCraft Agent는 LangGraph 기반 Multi-Agent 시스템으로, 사용자의 아이디어를 입력받아 자동으로 **웹/앱 서비스 기획서**를 생성합니다.

### 1.1 핵심 설계 원칙

- **6 Agent 협업**: 각자의 전문 역할을 수행하는 Agent 파이프라인
- **LangGraph Best Practice**: TypedDict + dict-access + Partial Update 패턴 100% 준수
- **자율 판단**: 사용자에게 질문하지 않고 RAG/웹 검색으로 정보 수집
- **Human-in-the-loop**: 불명확한 요청 시 `interrupt()` 패턴으로 사용자 인터랙션
- **자동 개선**: Reviewer 피드백을 Refiner가 직접 반영
- **Graceful Degradation**: 일부 실패해도 전체 시스템 동작 유지
- **Time-Travel Ready**: `MemorySaver` 체크포인터로 상태 롤백 지원

### 1.2 설계 철학

> "질문하지 않는 전문가" - 진정한 에이전트는 사용자에게 되묻지 않고, 가용한 정보를 최대한 활용하여 베스트 프랙티스를 제안합니다.

## 2. 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                              │
│                         (app.py)                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Workflow                            │
│                    (graph/workflow.py)                           │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ retrieve │→ │fetch_web │→ │ analyze  │→ │structure │        │
│  │  (RAG)   │  │(조건부)   │  │(자율판단) │  │          │        │
│  └──────────┘  └──────────┘  └────┬─────┘  └────┬─────┘        │
│                                   │              │               │
│                                   ▼              ▼               │
│                            ┌──────────┐  ┌──────────┐           │
│                            │  write   │→ │  review  │           │
│                            └──────────┘  └────┬─────┘           │
│                                               │                  │
│                                               ▼                  │
│                            ┌──────────┐  ┌──────────┐           │
│                            │  refine  │→ │  format  │→ END      │
│                            │(피드백반영)│  │ (요약)   │           │
│                            └──────────┘  └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  RAG/FAISS  │  │ Web Search  │  │ Azure OpenAI│
│             │  │  (Tavily)  │  │  (GPT-4o)   │
└─────────────┘  └─────────────┘  └─────────────┘
```

## 3. Agent 상세

### 3.1 Agent 구성

| Agent | 역할 | Temperature | 모델 | 출력 |
|-------|------|-------------|------|------|
| **Analyzer** | 입력 분석, 자율 판단으로 기획 방향 결정 | 0.3 | gpt-4o | `analysis` |
| **Structurer** | 기획서 섹션 구조 설계 | 0.5 | gpt-4o | `structure` |
| **Writer** | 섹션별 콘텐츠 작성 | 0.7 | gpt-4o | `draft` |
| **Reviewer** | 품질 검토, 개선점 도출 | 0.3 | gpt-4o | `review` |
| **Refiner** | 피드백 직접 반영하여 완성본 생성 | 0.5 | gpt-4o | `final_output` |
| **Formatter** | 채팅용 요약 메시지 생성 | 0.5 | gpt-4o-mini | `chat_summary` |

### 3.2 Agent 간 데이터 흐름

```
User Input
    │
    ▼
┌─────────┐    ┌───────────┐    ┌─────────┐
│Analyzer │───▶│ Structurer│───▶│ Writer  │
│         │    │           │    │         │
│analysis │    │ structure │    │  draft  │
└─────────┘    └───────────┘    └────┬────┘
                                     │
                                     ▼
                              ┌─────────┐
                              │Reviewer │
                              │         │
                              │ review  │
                              └────┬────┘
                                   │
                                   ▼
┌─────────┐                 ┌─────────┐
│Formatter│◀────────────────│ Refiner │
│         │                 │         │
│chat_sum │                 │final_out│
└─────────┘                 └─────────┘
```

## 4. 데이터 흐름 (State)

### 4.1 TypedDict 기반 상태 관리 (LangGraph Best Practice)

```python
# graph/state.py
class PlanCraftState(TypedDict, total=False):
    """LangGraph 공식 권장 패턴: TypedDict + dict-access"""

    # ========== Input Fields ==========
    user_input: str              # 사용자 입력
    file_content: Optional[str]  # 업로드 파일
    thread_id: str               # 세션 식별자

    # ========== Output Fields ==========
    final_output: Optional[str]  # 최종 기획서
    chat_summary: Optional[str]  # 채팅용 요약
    step_history: List[dict]     # 단계별 실행 이력

    # ========== Internal Fields ==========
    rag_context: Optional[str]   # RAG 검색 결과
    web_context: Optional[str]   # 웹 검색 결과
    web_urls: Optional[List]     # 조회한 URL 목록
    analysis: Optional[dict]     # Analyzer 출력 (dict로 저장)
    structure: Optional[dict]    # Structurer 출력
    draft: Optional[dict]        # Writer 출력
    review: Optional[dict]       # Reviewer 출력
    need_more_info: bool         # 추가 정보 필요 여부
    refined: bool                # 개선 작업 수행 여부

    # ========== Metadata ==========
    current_step: str            # 현재 처리 단계
    step_status: Literal["RUNNING", "SUCCESS", "FAILED"]
    refine_count: int            # 개선 루프 카운트 (0~3)
    error: Optional[str]         # 오류 메시지

    # ========== Interrupt & Routing ==========
    confirmed: Optional[bool]
    routing_decision: Optional[str]
```

### 4.2 헬퍼 함수

```python
# 상태 생성
state = create_initial_state("점심 메뉴 추천 앱")

# 상태 업데이트 (불변성 보장 - 새 dict 반환)
new_state = update_state(state, current_step="analyze", analysis=result)

# 안전한 값 추출 (dict/Pydantic 양쪽 호환)
topic = safe_get(analysis, "topic", "")

# 상태 검증
assert validate_state(state), "Expected dict"
```

## 5. 핵심 로직

### 5.1 Analyzer - 자율 판단

```python
# prompts/analyzer_prompt.py
"""
핵심 원칙: 질문하지 않고 바로 실행!

절대 질문하지 마세요. 진정한 전문가는 고객에게 되묻지 않습니다.
- RAG 검색 결과 → 내부 가이드/사례 적극 활용
- 웹 검색 결과 → 최신 트렌드/시장 정보 반영
- 부족한 정보 → 업계 베스트 프랙티스로 채움
- 모호한 요청 → 가장 합리적인 방향 선택

assumptions 필드에 내가 결정한 사항들을 기록
"""
```

### 5.2 Refiner - 피드백 반영

```python
# agents/refiner.py
"""
Reviewer가 지적한 개선점을 직접 반영하여 완성본 생성

점수 9점 이상 + 개선점 없음 → 수정 없이 통과
그 외 → 모든 개선점과 제안사항을 직접 반영
"""
```

### 5.3 조건부 웹 검색

```python
# mcp/web_search.py
def should_search_web(user_input, rag_context):
    """
    웹 검색 수행 조건:
    1. 최신성 키워드 감지 ("최근", "2025", "트렌드")
    2. 외부 정보 키워드 감지 ("시장", "경쟁사", "업계")

    웹 검색 스킵 조건:
    1. URL 직접 제공 (URL fetch로 대체)
    2. RAG 컨텍스트 충분
    """
```

### 5.4 Refinement Loop (기획서 고도화)

- **Loop Structure**: 사용자 피드백을 받아 최대 3회까지 기획서 수정 가능
- **Context Injection**:
    - `user_input`: 누적된 피드백 (기존 요청 + 추가 요청)
    - `previous_plan`: 직전 버전의 기획서 내용 (Agent가 참고하여 수정)
- **Versioning**: 세션 내에서 생성된 모든 기획서 버전을 `plan_history`에 저장 및 조회 가능

## 6. 기술 스택

| 계층 | 기술 |
|------|------|
| UI | Streamlit |
| Workflow | LangGraph |
| LLM Framework | LangChain |
| LLM | Azure OpenAI (GPT-4o, GPT-4o-mini) |
| Vector DB | FAISS |
| Embedding | text-embedding-3-large |
| Web Search | Tavily |
| Validation | Pydantic (Agent 스키마) |
| State Management | TypedDict + update_state() |
| Checkpointing | LangGraph MemorySaver |

## 7. 확장 포인트

- **Agent 추가**: `agents/` 폴더에 새 Agent 정의 후 `workflow.py`에 등록
- **프롬프트 수정**: `prompts/` 폴더의 해당 파일 수정
- **RAG 문서 추가**: `rag/documents/`에 마크다운 파일 추가 후 재인덱싱
- **웹 검색 조건 추가**: `tools/web_search.py`의 키워드 목록 수정
- **State 필드 추가**: `graph/state.py`의 `PlanCraftState` TypedDict에 필드 추가

## 8. LangGraph Best Practice 적용 현황

| 항목 | 적용 상태 | 구현 위치 |
|------|----------|-----------|
| TypedDict State | ✅ | `graph/state.py` |
| dict-access 패턴 | ✅ | 모든 Agent, 노드 |
| Partial Update | ✅ | `update_state()` 헬퍼 |
| Input/Output 분리 | ✅ | `PlanCraftInput`, `PlanCraftOutput` |
| Sub-graph | ✅ | `graph/subgraphs.py` |
| Human-in-the-loop | ✅ | `interrupt()` + `Command` |
| Time-Travel | ✅ | `MemorySaver` 체크포인터 |
| Conditional Edges | ✅ | `should_ask_user()` |
