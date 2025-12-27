"""
PlanCraft Agent - Sub-graph 정의 모듈

LangGraph 베스트 프랙티스에 따라 관련 노드들을 Sub-graph로 그룹화합니다.
각 Sub-graph는 명확한 책임을 가지며, 독립적으로 테스트/재사용 가능합니다.

Sub-graph 구조:
    1. Context Sub-graph: 정보 수집 (RAG + 웹 검색)
    2. Generation Sub-graph: 콘텐츠 생성 (분석 → 구조 → 작성)
    3. QA Sub-graph: 품질 관리 (검토 → 개선 → 포맷)

Best Practice:
    - 각 Sub-graph는 독립적으로 컴파일 가능
    - 메인 Graph에서 Sub-graph를 노드로 추가
    - 명확한 책임 분리로 유지보수성 향상
"""

from langgraph.graph import StateGraph, END
from graph.state import PlanCraftState
from agents import analyzer, structurer, writer, reviewer, refiner, formatter


# =============================================================================
# Context Sub-graph: 정보 수집 단계
# =============================================================================

def create_context_subgraph() -> StateGraph:
    """
    Context Sub-graph 생성
    
    책임: RAG 검색 + 조건부 웹 검색
    입력: user_input, file_content
    출력: rag_context, web_context
    """
    from graph.workflow import retrieve_context, fetch_web_context
    
    subgraph = StateGraph(PlanCraftState)
    
    # 노드 등록
    subgraph.add_node("rag_retrieve", retrieve_context)
    subgraph.add_node("web_fetch", fetch_web_context)
    
    # 흐름 정의: RAG → 웹 검색 (순차)
    subgraph.set_entry_point("rag_retrieve")
    subgraph.add_edge("rag_retrieve", "web_fetch")
    subgraph.add_edge("web_fetch", END)
    
    return subgraph


# =============================================================================
# Generation Sub-graph: 콘텐츠 생성 단계
# =============================================================================

def create_generation_subgraph() -> StateGraph:
    """
    Generation Sub-graph 생성
    
    책임: 분석 → 구조 설계 → 초안 작성
    입력: rag_context, web_context, user_input
    출력: analysis, structure, draft
    """
    subgraph = StateGraph(PlanCraftState)
    
    # 노드 등록
    subgraph.add_node("analyze", analyzer.run)
    subgraph.add_node("structure", structurer.run)
    subgraph.add_node("write", writer.run)
    
    # 흐름 정의
    subgraph.set_entry_point("analyze")
    subgraph.add_edge("analyze", "structure")
    subgraph.add_edge("structure", "write")
    subgraph.add_edge("write", END)
    
    return subgraph


# =============================================================================
# QA Sub-graph: 품질 관리 단계
# =============================================================================

def create_qa_subgraph() -> StateGraph:
    """
    QA (Quality Assurance) Sub-graph 생성
    
    책임: 검토 → 개선 → 최종 포맷팅
    입력: draft
    출력: review, final_output, chat_summary
    """
    subgraph = StateGraph(PlanCraftState)
    
    # 노드 등록
    subgraph.add_node("review", reviewer.run)
    subgraph.add_node("refine", refiner.run)
    subgraph.add_node("format", formatter.run)
    
    # 흐름 정의
    subgraph.set_entry_point("review")
    subgraph.add_edge("review", "refine")
    subgraph.add_edge("refine", "format")
    subgraph.add_edge("format", END)
    
    return subgraph


# =============================================================================
# Sub-graph 컴파일 (독립 테스트용)
# =============================================================================

def get_context_app():
    """Context Sub-graph 컴파일된 앱 반환"""
    return create_context_subgraph().compile()


def get_generation_app():
    """Generation Sub-graph 컴파일된 앱 반환"""
    return create_generation_subgraph().compile()


def get_qa_app():
    """QA Sub-graph 컴파일된 앱 반환"""
    return create_qa_subgraph().compile()


# =============================================================================
# Sub-graph 실행 래퍼 (메인 Graph에서 노드로 사용)
# =============================================================================

def run_context_subgraph(state: PlanCraftState) -> PlanCraftState:
    """
    Context Sub-graph 실행 래퍼
    
    메인 Graph에서 단일 노드로 호출됩니다.
    내부적으로 RAG + 웹 검색을 순차 실행합니다.
    """
    app = get_context_app()
    result = app.invoke(state)
    
    if hasattr(result, "model_copy"):
        return result
    # dict인 경우 PlanCraftState로 변환
    return state.model_copy(update=result)


def run_generation_subgraph(state: PlanCraftState) -> PlanCraftState:
    """
    Generation Sub-graph 실행 래퍼
    
    메인 Graph에서 단일 노드로 호출됩니다.
    내부적으로 분석 → 구조 → 작성을 순차 실행합니다.
    """
    app = get_generation_app()
    result = app.invoke(state)
    
    if hasattr(result, "model_copy"):
        return result
    return state.model_copy(update=result)


def run_qa_subgraph(state: PlanCraftState) -> PlanCraftState:
    """
    QA Sub-graph 실행 래퍼
    
    메인 Graph에서 단일 노드로 호출됩니다.
    내부적으로 검토 → 개선 → 포맷을 순차 실행합니다.
    """
    app = get_qa_app()
    result = app.invoke(state)
    
    if hasattr(result, "model_copy"):
        return result
    return state.model_copy(update=result)
