"""
PlanCraft Agent - LangGraph 워크플로우 정의

Multi-Agent 파이프라인을 LangGraph StateGraph로 정의합니다.
각 Agent는 노드로 등록되며, 조건부 엣지를 통해 흐름을 제어합니다.

워크플로우 구조:
    
            ┌──────────────┐
            │    START     │
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │   retrieve   │  <- RAG (내부 가이드 검색)
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │  fetch_web   │  <- MCP (조건부 웹 검색)
            └──────┬───────┘
                   │
            ┌──────▼───────┐      need_more_info=True     ┌─────────┐
            │   analyze    │ ───────────────────────────▶ │   END   │
            └──────┬───────┘      (질문 생성 및 중단)      └─────────┘
                   │
                   │ need_more_info=False (자동 진행)
                   ▼
            ┌──────▼───────┐
            │  structure   │  <- 기획서 목차/구조 설계
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │    write     │  <- 섹션별 내용 작성 (초안)
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │    review    │  <- Judge (PASS/REVISE/FAIL 판정)
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │    refine    │  <- 판정에 따른 개선/재작성
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │    format    │  <- 채팅 요약 생성
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │     END      │
            └──────────────┘

Best Practice 적용:
    - InputState/OutputState 분리: API 경계 명확화
    - PlanCraftState 타입 어노테이션: 모든 노드 함수에 적용

사용 예시:
    from graph.workflow import run_plancraft

    result = run_plancraft("점심 메뉴 추천 앱을 만들고 싶어요")
    print(result["final_output"])
"""

from langgraph.graph import StateGraph, END
from graph.state import PlanCraftState
from agents import analyzer, structurer, writer, reviewer, refiner, formatter
from utils.config import Config

# =============================================================================
# LangSmith 트레이싱 활성화 (Observability)
# =============================================================================
Config.setup_langsmith()


# =============================================================================
# 노드 함수 정의 (모두 PlanCraftState 타입 명시)
# =============================================================================

# =============================================================================
# 노드 함수 정의 (모두 PlanCraftState Pydantic 모델 사용)
# =============================================================================

def retrieve_context(state: PlanCraftState) -> PlanCraftState:
    """RAG 검색 노드"""
    try:
        from rag.retriever import Retriever

        # Retriever 초기화 (상위 3개 문서 검색)
        retriever = Retriever(k=3)

        # 사용자 입력으로 관련 문서 검색
        user_input = state.user_input
        context = retriever.get_formatted_context(user_input)

        new_state = state.model_copy(update={
            "rag_context": context,
            "current_step": "retrieve"
        })

    except Exception as e:
        # RAG 실패 시에도 계속 진행
        new_state = state.model_copy(update={
            "rag_context": "",
            "error": f"RAG 검색 실패: {str(e)}"
        })

    return new_state


def fetch_web_context(state: PlanCraftState) -> PlanCraftState:
    """
    조건부 웹 정보 수집 노드
    
    MCP_ENABLED=true: MCPToolkit (Fetch + Tavily) 사용
    MCP_ENABLED=false: Fallback 모드 (requests + DuckDuckGo)
    """
    import re
    from utils.config import Config

    user_input = state.user_input
    rag_context = state.rag_context
    web_contents = []
    web_urls = []

    try:
        # 1. URL이 직접 제공된 경우 -> URL Fetch
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, user_input)

        if urls:
            # MCP 또는 Fallback으로 URL Fetch
            from mcp.mcp_client import fetch_url_sync

            for url in urls[:3]:  # 최대 3개 URL
                try:
                    content = fetch_url_sync(url, max_length=3000)
                    if content and not content.startswith("[웹 조회 실패"):
                        web_contents.append(f"[URL 참조: {url}]\n{content}")
                        web_urls.append(url)
                except Exception as e:
                    print(f"[WARN] URL 조회 실패 ({url}): {e}")

            print(f"[INFO] URL 직접 참조: {len(web_urls)}개")

        # 2. URL이 없으면 조건부 웹 검색 판단
        else:
            # MCP 모드: Tavily 사용, Fallback: DuckDuckGo
            from mcp.mcp_client import search_sync
            from mcp.web_search import should_search_web

            # 검색 필요 여부 판단
            decision = should_search_web(user_input, rag_context if rag_context else "")

            if decision["should_search"]:
                search_result = search_sync(decision["search_query"])
                
                if search_result["success"]:
                    # 결과 포맷팅
                    source = search_result.get("source", "unknown")
                    if "formatted" in search_result:
                        context = search_result["formatted"]
                    else:
                        context = str(search_result.get("results", ""))
                    
                    web_contents.append(
                        f"[웹 검색 결과 - {decision['reason']}]\n"
                        f"검색어: {decision['search_query']}\n"
                        f"출처: {source}\n\n"
                        f"{context}"
                    )
                    print(f"[INFO] 웹 검색 수행 ({source}): {decision['reason']}")
                else:
                    print(f"[WARN] 웹 검색 실패: {search_result.get('error', 'unknown')}")
            else:
                print(f"[INFO] 웹 검색 스킵: {decision['reason']}")

        # 3. 상태 업데이트
        web_context_str = "\n\n---\n\n".join(web_contents) if web_contents else None
        
        new_state = state.model_copy(update={
            "web_context": web_context_str,
            "web_urls": web_urls,
            "current_step": "fetch_web"
        })

    except Exception as e:
        # 웹 조회 실패 시에도 계속 진행
        print(f"[WARN] 웹 조회 단계 오류: {e}")
        new_state = state.model_copy(update={
            "web_context": None,
            "web_urls": [],
            "error": f"웹 조회 오류: {str(e)}"
        })

    return new_state


def should_ask_user(state: PlanCraftState) -> str:
    """조건부 라우터"""
    if state.need_more_info:
        return "ask_user"  # 추가 정보 필요
    return "continue"       # 계속 진행


# =============================================================================
# 워크플로우 생성
# =============================================================================

def create_workflow() -> StateGraph:
    """PlanCraft 워크플로우 생성 (기본 버전)"""
    # Pydantic 모델을 State로 사용
    workflow = StateGraph(PlanCraftState)

    # 노드 등록
    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("fetch_web", fetch_web_context)
    workflow.add_node("analyze", analyzer.run)
    workflow.add_node("structure", structurer.run)
    workflow.add_node("write", writer.run)
    workflow.add_node("review", reviewer.run)
    workflow.add_node("refine", refiner.run)
    workflow.add_node("format", formatter.run)

    # 엣지 정의
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "fetch_web")
    workflow.add_edge("fetch_web", "analyze")

    workflow.add_conditional_edges(
        "analyze",
        should_ask_user,
        {
            "ask_user": END,
            "continue": "structure"
        }
    )

    workflow.add_edge("structure", "write")
    workflow.add_edge("write", "review")
    workflow.add_edge("review", "refine")
    workflow.add_edge("refine", "format")
    workflow.add_edge("format", END)

    return workflow


# =============================================================================
# Sub-graph 패턴 워크플로우 (Best Practice)
# =============================================================================

def create_subgraph_workflow() -> StateGraph:
    """
    PlanCraft 워크플로우 생성 (Sub-graph 패턴)
    
    LangGraph 베스트 프랙티스에 따라 관련 노드들을 Sub-graph로 그룹화합니다.
    
    구조:
        ┌─────────────────────────────────────────────────────────┐
        │                    Main Graph                           │
        │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
        │  │   Context    │  │  Generation  │  │      QA      │  │
        │  │  Sub-graph   │→│  Sub-graph   │→│  Sub-graph   │  │
        │  │ (RAG + Web)  │  │(분석→구조→작성)│  │(검토→개선→포맷)│  │
        │  └──────────────┘  └──────────────┘  └──────────────┘  │
        └─────────────────────────────────────────────────────────┘
    
    장점:
        - 명확한 책임 분리 (SRP)
        - 각 Sub-graph 독립 테스트 가능
        - 코드 재사용성 향상
        - 복잡한 워크플로우 관리 용이
    """
    from graph.subgraphs import (
        run_context_subgraph,
        run_generation_subgraph,
        run_qa_subgraph
    )
    
    workflow = StateGraph(PlanCraftState)
    
    # Sub-graph를 단일 노드로 등록
    workflow.add_node("context_gathering", run_context_subgraph)
    workflow.add_node("content_generation", run_generation_subgraph)
    workflow.add_node("quality_assurance", run_qa_subgraph)
    
    # 흐름 정의
    workflow.set_entry_point("context_gathering")
    
    # Context → Generation (조건부 분기)
    def should_continue_to_generation(state: PlanCraftState) -> str:
        """Generation으로 진행할지 판단"""
        if state.need_more_info:
            return "ask_user"
        return "continue"
    
    workflow.add_conditional_edges(
        "context_gathering",
        should_continue_to_generation,
        {
            "ask_user": END,
            "continue": "content_generation"
        }
    )
    
    workflow.add_edge("content_generation", "quality_assurance")
    workflow.add_edge("quality_assurance", END)
    
    return workflow


def compile_workflow(use_subgraphs: bool = False):
    """워크플로우 컴파일"""
    if use_subgraphs:
        return create_subgraph_workflow().compile()
    return create_workflow().compile()


# 전역 앱 인스턴스
app = compile_workflow()


# =============================================================================
# 실행 함수
# =============================================================================

def run_plancraft(user_input: str, file_content: str = None) -> dict:
    """
    PlanCraft Agent 워크플로우 실행
    
    UI 계층과의 호환성을 위해 최종 결과는 dict 형태로 반환합니다.
    """
    from graph.state import create_initial_state

    # 초기 상태 생성 (Pydantic 객체 리턴)
    initial_state = create_initial_state(user_input, file_content)

    # 워크플로우 실행 (invoke는 dict 또는 BaseModel을 받음)
    final_state = app.invoke(initial_state)

    # UI 계층에서는 dict 처리가 되어 있으므로 변환하여 반환
    if hasattr(final_state, "model_dump"):
        return final_state.model_dump()
    return final_state
