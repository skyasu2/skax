# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlanCraft Agent는 LangGraph, Azure OpenAI, Streamlit 기반의 AI 멀티 에이전트 기획서 자동 생성 시스템입니다.

### 서비스 핵심 흐름
```
사용자 입력
    ↓
[간단한 질문?] ─YES→ AI 직접 답변 (기획서 생성 X)
    │NO
    ↓
[입력이 부실?] ─YES→ 프롬프트 증폭기 (AI가 컨셉 확장 제안)
    │NO
    ↓
기획서 생성 (6개 Agent 협업)
    ↓
1차 기획안 완성 → 사용자 수정 요청 (최대 3회)
```

### 핵심 원칙
- **간단한 질문**: `is_general_query=True` → 기획서 없이 AI 직접 답변
- **프롬프트 증폭기**: 20자 미만 입력 시 AI가 유사 컨셉 옵션 제시 (HITL)
- **사용자 수정 3회**: 1차 완성 **후** 추가 피드백으로 고도화 가능
- **브레인스토밍**: 아이디어 없을 때 사용하는 **보조 기능**

### 품질 루프 vs 사용자 수정 (별개!)
| 구분 | 내부 품질 루프 | 사용자 수정 |
|------|--------------|------------|
| 시점 | 기획서 완성 **전** | 기획서 완성 **후** |
| 주체 | Reviewer (자동) | 사용자 (수동) |
| 횟수 | 최대 3회 (내부) | 최대 3회 (별도) |
| 트리거 | 점수 < 9점 | 사용자 피드백 입력 |

> Formatter에서 `refine_count=0` 리셋하여 두 카운터 분리

## Commands

### 실행
```bash
# 개발 모드
streamlit run app.py

# Docker
docker-compose up -d
```

### 테스트
```bash
# 전체 테스트
pytest tests/ -v

# CI 환경 (PYTHONPATH 설정 필요)
PYTHONPATH=$(pwd) pytest tests/ -v
```

### 의존성
```bash
pip install -r requirements.txt
```

## Architecture

### Agent Pipeline
```
User Input → [RAG + Web Search (병렬)] → Analyzer → Structurer → Writer → Reviewer → Refiner → Formatter → Output
```

### 핵심 컴포넌트

| 컴포넌트 | 위치 | 역할 |
|---------|------|------|
| State 관리 | `graph/state.py` | TypedDict 상태 + ensure_dict 유틸리티 |
| 워크플로우 | `graph/workflow.py` | StateGraph + RunnableBranch 라우팅 |
| 에이전트 | `agents/*.py` | 6개 전문 에이전트 |
| LLM 설정 | `utils/llm.py` | Azure OpenAI 클라이언트 팩토리 |
| 설정 | `utils/settings.py` | 중앙집중식 프로젝트 설정 |
| RAG | `rag/*.py` | FAISS + MMR 검색 (불변 가이드 문서) |
| 브레인스토밍 | `utils/idea_generator.py` | 8개 카테고리 아이디어 생성 |
| UI 스타일 | `ui/styles.py` | CSS Design Tokens |

### Reviewer 라우팅 (RunnableBranch 패턴)
```python
# 조건 함수
_is_max_restart_reached(state)  # 최대 복귀 횟수
_is_quality_fail(state)          # score < 5 또는 FAIL
_is_quality_pass(state)          # score >= 9 및 PASS

# 분기
< 5점 (FAIL)   → Analyzer 복귀 (최대 2회)
5-8점 (REVISE) → Discussion → Refiner (최대 3회)
≥ 9점 (PASS)   → Formatter 완료 (Discussion 건너뜀)
```

### Discussion SubGraph (에이전트 간 대화)
```
┌─────────────────────────────────────┐
│     Discussion SubGraph             │
│                                     │
│  reviewer_speak ──► writer_respond  │
│        ▲                 │          │
│        └──── NO ◄── check_consensus │
│                          │ YES      │
│                          ▼          │
│                         END         │
└─────────────────────────────────────┘

# State 필드
discussion_messages: List[dict]  # 대화 이력
discussion_round: int            # 라운드 수
consensus_reached: bool          # 합의 도달
agreed_action_items: List[str]   # 합의된 개선 사항
```

### RAG vs 웹검색 역할 분리
| 소스 | 역할 | 데이터 특성 |
|------|------|------------|
| RAG (FAISS) | 작성 방법론, 체크리스트, 예시 | 불변 |
| 웹 검색 (Tavily) | 시장 규모, 트렌드, 경쟁사 | 실시간 |

## Key Patterns

### ensure_dict (Pydantic/Dict 일관성)
```python
from graph.state import ensure_dict

# LLM 결과를 항상 dict로 변환
result_dict = ensure_dict(llm_result)
```

### State 업데이트 (불변성 유지)
```python
from graph.state import update_state, safe_get

new_state = update_state(state, current_step="analyze", analysis=result)
topic = safe_get(analysis, "topic", "Unknown")
```

### 에이전트 구현 패턴
```python
from graph.state import PlanCraftState, update_state, ensure_dict

def run(state: PlanCraftState) -> PlanCraftState:
    result = llm.invoke(messages)
    result_dict = ensure_dict(result)  # Pydantic → Dict
    return update_state(state, analysis=result_dict)
```

### 에러 핸들링 데코레이터
```python
from utils.error_handler import handle_node_error

@handle_node_error
def node_function(state: PlanCraftState) -> PlanCraftState:
    pass
```

### Self-reflection 패턴 (Writer 예시)
```python
# LLM 결과를 자체 검증 후 재시도
max_retries = 3
while current_try < max_retries:
    result = llm.invoke(messages)
    sections = result.get("sections", [])

    # Self-Check: 최소 요구사항 검증
    if len(sections) < MIN_SECTIONS:
        messages.append({"role": "user", "content": "섹션이 부족합니다. 재작성하세요."})
        current_try += 1
        continue

    break  # 검증 통과
```

### HITL Resume 로깅 (step_history)
```python
# 사용자 Resume 입력이 step_history에 자동 기록됨
# graph/interrupt_utils.py의 handle_user_response() 참조
{
    "step": "human_resume",
    "status": "USER_INPUT",
    "summary": "옵션 선택: AI 헬스케어 앱",
    "response_data": {...}  # 민감정보 마스킹됨
}
```

## Configuration

### 필수 환경변수 (.env)
```env
AOAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_API_KEY=your_api_key
AOAI_DEPLOY_GPT4O=gpt-4o
AOAI_DEPLOY_GPT4O_MINI=gpt-4o-mini
AOAI_DEPLOY_EMBED_3_LARGE=text-embedding-3-large
```

### 선택 환경변수
```env
TAVILY_API_KEY=...           # 웹 검색
LANGCHAIN_TRACING_V2=true    # LangSmith 추적
LANGCHAIN_PROJECT=PlanCraft  # LangSmith 프로젝트명
CHECKPOINTER_TYPE=memory     # memory|postgres|redis
```

## File Modification Guide

| 작업 | 수정 파일 |
|-----|----------|
| 에이전트 로직 | `agents/{agent_name}.py` |
| 프롬프트 | `prompts/{agent_name}_prompt.py` |
| State 필드 | `graph/state.py` |
| 라우팅 조건 | `graph/workflow.py` (_is_quality_* 함수) |
| UI 스타일 | `ui/styles.py` (CSS 변수) |
| 브레인스토밍 카테고리 | `utils/prompt_examples.py` |
| RAG 문서 | `rag/documents/*.md` |

## Notes

- **TypedDict**: Pydantic 대신 가벼운 TypedDict로 LangGraph 상태 관리
- **ensure_dict**: 모든 에이전트에서 LLM 결과를 dict로 변환
- **불변성**: 항상 `update_state()`로 새 state dict 생성
- **로깅**: `get_file_logger()` → `/logs/` 디렉토리
- **에러 처리**: 모든 노드에 `@handle_node_error` 적용
- **Writer 검증**: 최소 9개 섹션, 마크다운 테이블, 최대 3회 재시도
- **시간 인식**: `time_context.py`로 연도/분기 정보 제공
