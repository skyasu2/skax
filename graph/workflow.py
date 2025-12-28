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
from langgraph.checkpoint.memory import MemorySaver  # [NEW] 체크포인터 추가
from graph.state import PlanCraftState
from agents import analyzer, structurer, writer, reviewer, refiner, formatter
from utils.config import Config
from utils.file_logger import get_file_logger  # 로거 추가

# =============================================================================
# LangSmith 트레이싱 활성화 (Observability)
# =============================================================================
Config.setup_langsmith()


# =============================================================================
# Helper: 실행 이력 기록 및 로깅 통합
# =============================================================================

def _update_step_history(state: PlanCraftState, step: str, status: str, summary: str = "", error: str = None) -> PlanCraftState:
    """
    [Internal] 실행 이력을 State에 기록하고, 파일 로그를 남긴 후 업데이트된 State를 반환합니다.
    """
    from datetime import datetime
    
    # 1. History Item 생성
    history_item = {
        "step": step,
        "status": status,
        "summary": summary,
        "error": error,
        "timestamp": datetime.now().isoformat()
    }
    
    # 2. Immutable Update (List append)
    new_history = list(state.step_history) + [history_item]
    
    # 3. State 업데이트
    updates = {
        "step_history": new_history,
        "current_step": step,
        "step_status": status,
        "last_error": error
    }
    
    updated_state = state.model_copy(update=updates)
    
    # 4. 파일 로깅 (통합)
    get_file_logger().log(step, updated_state)
    
    return updated_state


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

    # [LOG] 실행 결과 로깅 및 히스토리 업데이트
    status = "FAILED" if new_state.error else "SUCCESS"
    summary = f"검색된 문서: {len(new_state.rag_context.split('---')) if new_state.rag_context else 0}건"
    
    return _update_step_history(new_state, "retrieve", status, summary, new_state.error)


def fetch_web_context(state: PlanCraftState) -> PlanCraftState:
    """
    조건부 웹 정보 수집 노드
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
            from tools.mcp_client import fetch_url_sync

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
            from tools.mcp_client import search_sync
            from tools.web_search import should_search_web

            # 검색 필요 여부 판단 (항상 True에 가깝게 변경됨)
            decision = should_search_web(user_input, rag_context if rag_context else "")

            if decision["should_search"]:
                base_query = decision["search_query"]
                
                # 검색 쿼리 확장
                queries = [base_query]
                if "트렌드" in base_query:
                    queries.append(base_query.replace("트렌드", "시장 규모 통계"))
                else:
                    queries.append(f"{base_query} 시장 규모 및 경쟁사")
                
                print(f"[INFO] 다중 웹 검색 수행 (총 {len(queries)}회): {queries}")
                
                for i, q in enumerate(queries):
                    search_result = search_sync(q)
                    
                    if search_result["success"]:
                        # 결과 포맷팅
                        source = search_result.get("source", "unknown")
                        formatted_result = ""
                        
                        # 상세 결과에서 URL 추출 및 포맷팅
                        if "results" in search_result and isinstance(search_result["results"], list):
                            for idx, res in enumerate(search_result["results"][:3]): # 상위 3개만
                                title = res.get("title", "제목 없음")
                                url = res.get("url", "URL 없음")
                                snippet = res.get("snippet", "")[:200]
                                formatted_result += f"- [{title}]({url})\n  {snippet}\n"
                        
                        # fallback: 포맷된 결과가 없으면 기존 방식 사용
                        if not formatted_result and "formatted" in search_result:
                            formatted_result = search_result["formatted"]
                            
                        web_contents.append(
                            f"[웹 검색 결과 {i+1} - {q}]\n"
                            f"{formatted_result}"
                        )
                    else:
                        print(f"[WARN] 검색 실패 ({q}): {search_result.get('error')}")
            else:
                print(f"[INFO] 웹 검색 스킵: {decision['reason']}")

        # 3. 상태 업데이트
        existing_context = state.web_context
        existing_urls = state.web_urls or []
        
        new_context_str = "\n\n---\n\n".join(web_contents) if web_contents else None
        
        final_context = existing_context
        if new_context_str:
            if final_context:
                final_context = f"{final_context}\n\n{new_context_str}"
            else:
                final_context = new_context_str
                
        # URL 합치기
        final_urls = list(dict.fromkeys(existing_urls + web_urls))
        
        new_state = state.model_copy(update={
            "web_context": final_context,
            "web_urls": final_urls,
            "current_step": "fetch_web"
        })

    except Exception as e:
        print(f"[WARN] 웹 조회 단계 오류: {e}")
        new_state = state.model_copy(update={
            "web_context": None,
            "web_urls": [],
            "error": f"웹 조회 오류: {str(e)}"
        })

    # [LOG] 실행 결과 로깅 및 히스토리 업데이트
    status = "FAILED" if new_state.error else "SUCCESS"
    url_count = len(new_state.web_urls) if new_state.web_urls else 0
    summary = f"웹 정보 수집: {url_count}개 URL 참조"
    
    return _update_step_history(new_state, "fetch_web", status, summary, new_state.error)


def should_ask_user(state: PlanCraftState) -> str:
    """
    조건부 라우터 (RunnableBranch 스타일 분기)
    
    분기 조건:
      1. need_more_info = True → "ask_user" (휴먼 인터럽트)
      2. is_general_query = True → "ask_user" (일반 응답)
      3. 그 외 → "continue" (기획서 생성 계속)
    
    Returns:
        str: "ask_user" 또는 "continue"
    """
    # 조건 1: 추가 정보 요청 (옵션 선택 필요)
    if state.need_more_info:
        return "ask_user"
    
    # 조건 2: 일반 질의 (기획 요청이 아님)
    is_general = state.analysis.is_general_query if state.analysis else False
    if is_general:
        return "ask_user"
    
    # 기본: 기획서 생성 계속
    return "continue"


# -----------------------------------------------------------------------------
# [NEW] RunnableBranch 스타일 분기 조건 함수들 (확장용)
# -----------------------------------------------------------------------------

def is_human_interrupt_required(state: PlanCraftState) -> bool:
    """휴먼 인터럽트가 필요한지 확인"""
    return state.need_more_info is True


def is_general_query(state: PlanCraftState) -> bool:
    """일반 질의인지 확인 (기획 요청이 아님)"""
    if not state.analysis:
        return False
    return getattr(state.analysis, "is_general_query", False)


def is_plan_generation_ready(state: PlanCraftState) -> bool:
    """기획서 생성 준비가 되었는지 확인"""
    return not is_human_interrupt_required(state) and not is_general_query(state)


def get_routing_decision(state: PlanCraftState) -> dict:
    """
    상태 기반 라우팅 결정을 반환 (디버깅/로깅용)
    
    Returns:
        dict: {
            "decision": str,
            "reason": str,
            "conditions": dict
        }
    """
    conditions = {
        "need_more_info": state.need_more_info,
        "is_general_query": is_general_query(state),
        "has_analysis": state.analysis is not None
    }
    
    if is_human_interrupt_required(state):
        return {
            "decision": "ask_user",
            "reason": "추가 정보 필요 (옵션 선택 대기)",
            "conditions": conditions
        }
    
    if is_general_query(state):
        return {
            "decision": "ask_user", 
            "reason": "일반 질의 (기획 요청 아님)",
            "conditions": conditions
        }
    
    return {
        "decision": "continue",
        "reason": "기획서 생성 진행",
        "conditions": conditions
    }


# =============================================================================
# Agent 래퍼 함수 (Logging Wrapper)
# =============================================================================

def run_analyzer_node(state: PlanCraftState) -> PlanCraftState:
    new_state = analyzer.run(state)
    
    status = "FAILED" if new_state.error else "SUCCESS"
    topic = new_state.analysis.topic if new_state.analysis else "분석 실패"
    summary = f"주제 분석: {topic}"
    
    return _update_step_history(new_state, "analyze", status, summary, new_state.error)

def run_structurer_node(state: PlanCraftState) -> PlanCraftState:
    new_state = structurer.run(state)
    
    status = "FAILED" if new_state.error else "SUCCESS"
    sec_count = len(new_state.structure.sections) if new_state.structure else 0
    summary = f"구조 설계: {sec_count}개 섹션"
    
    return _update_step_history(new_state, "structure", status, summary, new_state.error)

def run_writer_node(state: PlanCraftState) -> PlanCraftState:
    new_state = writer.run(state)
    
    status = "FAILED" if new_state.error else "SUCCESS"
    draft_status = "작성 완료" if new_state.draft else "작성 실패"
    summary = f"초안 작성: {draft_status}"
    
    return _update_step_history(new_state, "write", status, summary, new_state.error)

def run_reviewer_node(state: PlanCraftState) -> PlanCraftState:
    new_state = reviewer.run(state)
    
    status = "FAILED" if new_state.error else "SUCCESS"
    verdict = new_state.review.verdict if new_state.review else "UNKNOWN"
    summary = f"품질 검토: {verdict}"
    
    return _update_step_history(new_state, "review", status, summary, new_state.error)

def run_refiner_node(state: PlanCraftState) -> PlanCraftState:
    new_state = refiner.run(state)
    
    status = "FAILED" if new_state.error else "SUCCESS"
    summary = f"기획서 개선: {state.refine_count}회차 수행"
    
    return _update_step_history(new_state, "refine", status, summary, new_state.error)

def run_formatter_node(state: PlanCraftState) -> PlanCraftState:
    new_state = formatter.run(state)
    
    status = "FAILED" if new_state.error else "SUCCESS"
    summary = "최종 포맷팅 및 요약 완료"
    
    return _update_step_history(new_state, "format", status, summary, new_state.error)


# =============================================================================
# 워크플로우 생성
# =============================================================================

def create_workflow() -> StateGraph:
    """PlanCraft 워크플로우 생성 (기본 버전)"""
    # Pydantic 모델을 State로 사용
    workflow = StateGraph(PlanCraftState)

    # 노드 등록 (래퍼 함수 사용)
    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("fetch_web", fetch_web_context)
    workflow.add_node("analyze", run_analyzer_node)
    workflow.add_node("structure", run_structurer_node)
    workflow.add_node("write", run_writer_node)
    workflow.add_node("review", run_reviewer_node)
    workflow.add_node("refine", run_refiner_node)
    workflow.add_node("format", run_formatter_node)

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
    # [NEW] 인메모리 체크포인터 사용 (Time-Travel 가능)
    checkpointer = MemorySaver()
    
    if use_subgraphs:
        return create_subgraph_workflow().compile(checkpointer=checkpointer)
    return create_workflow().compile(checkpointer=checkpointer)


# 전역 앱 인스턴스
app = compile_workflow()


# =============================================================================
# 실행 함수
# =============================================================================

def run_plancraft(
    user_input: str, 
    file_content: str = None, 
    refine_count: int = 0, 
    previous_plan: str = None,
    callbacks: list = None,
    thread_id: str = "default_thread"  # [NEW] 스레드 ID 지원
) -> dict:
    """
    PlanCraft Agent 워크플로우 실행
    """
    from graph.state import create_initial_state

    # 초기 상태 생성 (Pydantic 객체 리턴)
    initial_state = create_initial_state(user_input, file_content, previous_plan)
    
    # [중요] 개선 횟수 주입 (Agent들이 이를 참조하여 로직 수행)
    initial_state.refine_count = refine_count

    # 워크플로우 실행 (invoke는 dict 또는 BaseModel을 받음)
    # [NEW] Config에 thread_id 추가 (Checkpointer가 이를 식별)
    config = {"configurable": {"thread_id": thread_id}}
    
    if callbacks:
        config["callbacks"] = callbacks

    final_state = app.invoke(initial_state, config=config)

    # UI 계층에서는 dict 처리가 되어 있으므로 변환하여 반환
    if hasattr(final_state, "model_dump"):
        return final_state.model_dump()
    return final_state
