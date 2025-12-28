# PlanCraft Agent - 시스템 아키텍처

## 1. 시스템 개요

PlanCraft Agent는 LangGraph 기반 Multi-Agent 시스템으로, 사용자의 아이디어를 입력받아 자동으로 **웹/앱 서비스 기획서**를 생성합니다.

### 1.1 핵심 설계 원칙

- **6 Agent 협업**: 각자의 전문 역할을 수행하는 Agent 파이프라인
- **자율 판단**: 사용자에게 질문하지 않고 RAG/웹 검색으로 정보 수집
- **자동 개선**: Reviewer 피드백을 Refiner가 직접 반영
- **Graceful Degradation**: 일부 실패해도 전체 시스템 동작 유지

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
│             │  │ (DuckDuckGo)│  │  (GPT-4o)   │
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

```python
PlanCraftState (Pydantic Model)
├── user_input: str              # 사용자 입력
├── file_content: Optional[str]  # 업로드 파일
├── rag_context: Optional[str]   # RAG 검색 결과
├── web_context: Optional[str]   # 웹 검색 결과
├── web_urls: Optional[List]     # 조회한 URL 목록
├── analysis: Optional[AnalysisResult] # Analyzer 출력 (Pydantic)
├── need_more_info: bool         # 추가 정보 필요 여부
├── structure: Optional[StructureResult] # Structurer 출력 (Pydantic)
├── draft: Optional[DraftResult]     # Writer 출력 (Pydantic)
├── review: Optional[JudgeResult]    # Reviewer 출력 (Pydantic)
├── refined: bool                # 개선 작업 수행 여부
├── final_output: Optional[str]  # Refiner 출력 (개선된 기획서)
├── chat_summary: Optional[str]  # Formatter 출력 (채팅용 요약)
├── current_step: str            # 현재 처리 단계
├── refine_count: int            # [New] 추가 개선 루프 카운트 (0~3)
├── previous_plan: Optional[str] # [New] 이전 버전 기획서 (Refinement용)
└── error: Optional[str]         # 오류 메시지
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
| Web Search | DuckDuckGo (무료) |
| Validation | Pydantic |

## 7. 확장 포인트

- **Agent 추가**: `agents/` 폴더에 새 Agent 정의 후 `workflow.py`에 등록
- **프롬프트 수정**: `prompts/` 폴더의 해당 파일 수정
- **RAG 문서 추가**: `rag/documents/`에 마크다운 파일 추가 후 재인덱싱
- **웹 검색 조건 추가**: `mcp/web_search.py`의 키워드 목록 수정
