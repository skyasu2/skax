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
from langgraph.checkpoint.memory import MemorySaver  # 체크포인터
from langchain_core.runnables import RunnableBranch  # [NEW] 분기 패턴
from graph.state import PlanCraftState
from agents import analyzer, structurer, writer, reviewer, refiner, formatter
from utils.config import Config
from utils.file_logger import get_file_logger

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

@handle_node_error
def retrieve_context(state: PlanCraftState) -> PlanCraftState:
    """RAG 검색 노드"""
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

    # [LOG] 실행 결과 로깅 및 히스토리 업데이트
    status = "SUCCESS"
    summary = f"검색된 문서: {len(new_state.rag_context.split('---')) if new_state.rag_context else 0}건"
    
    return _update_step_history(new_state, "retrieve", status, summary)


@handle_node_error
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
      1. need_more_info = True → "option_pause" (휴먼 인터럽트)
      2. is_general_query = True → "general_response" (일반 응답)
      3. 그 외 → "continue" (기획서 생성 계속)
    
    Returns:
        str: "option_pause", "general_response", "continue"
    """
    # 조건 1: 추가 정보 요청 (옵션 선택 필요)
    if state.need_more_info:
        return "option_pause"
    
    # 조건 2: 일반 질의 (기획 요청이 아님)
    is_general = state.analysis.is_general_query if state.analysis else False
    if is_general:
        return "general_response"
    
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
# [NEW] RunnableBranch 기반 분기 체인 (공식 LangChain 패턴)
# =============================================================================

def create_routing_branch():
    """
    RunnableBranch를 사용한 분기 체인 생성
    
    공식 패턴에 따라 조건별 분기를 정의합니다.
    이 함수는 복잡한 분기가 필요할 때 사용할 수 있습니다.
    
    사용 예시:
        branch = create_routing_branch()
        result = branch.invoke(state)
    
    Returns:
        RunnableBranch: 분기 체인
    """
    return RunnableBranch(
        # 조건 1: 휴먼 인터럽트 필요 → 옵션 일시정지
        (
            lambda state: is_human_interrupt_required(state),
            lambda state: state.model_copy(update={"routing_decision": "ask_user"})
        ),
        # 조건 2: 일반 질의 → 일반 응답
        (
            lambda state: is_general_query(state),
            lambda state: state.model_copy(update={"routing_decision": "general_response"})
        ),
        # 기본: 기획서 생성 계속
        lambda state: state.model_copy(update={"routing_decision": "continue"})
    )


# =============================================================================
# [NEW] Interrupt 스타일 노드 (휴먼 인터럽트 처리)
# =============================================================================

# ... (기존 임포트 유지)

try:
    from langgraph.types import interrupt, Command
except ImportError:
    # LangGraph 구버전 또는 로컬 환경 호환성용 Mock
    def interrupt(value): return None
    class Command: pass


# ... (중간 코드 유지)


def option_pause_node(state: PlanCraftState) -> PlanCraftState:
    """
    휴먼 인터럽트 처리 노드 (LangGraph 공식 패턴 적용)
    
    이 노드는 실행을 일시 중단하고 사용자 입력을 기다립니다.
    
    동작 방식:
    1. interrupt(payload) 호출 → 실행 중단 (SUSPEND)
    2. 클라이언트(프론트엔드)에서 payload 확인 및 입력 UI 표시
    3. 사용자 입력 후 Command(resume=input)으로 재개
    4. interrupt()가 사용자 입력을 반환하며 실행 재개
    
    Returns:
        PlanCraftState: 사용자 입력이 반영된 상태
    """
    from graph.interrupt_utils import create_option_interrupt, handle_user_response
    
    # 1. 인터럽트 페이로드 생성
    payload = create_option_interrupt(state)
    payload["type"] = "option_selector"
    
    # 2. 실행 중단 및 사용자 응답 대기 (공식 패턴)
    #    로컬 Streamlit 앱의 경우, 여기서 중단되지 않고(Mock) None을 반환할 수 있음
    #    이 경우 기존 방식(status update)으로 fallback 처리
    try:
        user_response = interrupt(payload)
    except Exception:
        # interrupt가 지원되지 않는 환경이거나 에러 발생 시
        user_response = None
        
    # 3. 사용자 응답 처리 (Resume 후 실행됨)
    if user_response:
        # 사용자가 응답을 하고 재개한 경우
        new_state = handle_user_response(state, user_response)
        return _update_step_history(
            new_state,
            "option_pause",
            "RESUMED",
            summary="사용자 입력 수신 완료"
        )
    
    # 4. (Fallback) 아직 응답이 없거나 로컬 모드인 경우 - 기존 방식 유지
    new_state = state.model_copy(update={
        "current_step": "option_pause",
        "step_status": "WAITING_USER_INPUT"
    })
    
    return _update_step_history(
        new_state, 
        "option_pause", 
        "PAUSED",
        summary=f"사용자 입력 대기: {state.option_question or '옵션 선택'}"
    )


def general_response_node(state: PlanCraftState) -> PlanCraftState:
    """
    일반 질의 응답 노드
    
    기획 요청이 아닌 일반 질문에 대한 응답을 처리합니다.
    
    Returns:
        PlanCraftState: 응답이 포함된 상태
    """
    answer = "일반 질의에 대한 응답입니다."
    
    if state.analysis and hasattr(state.analysis, "general_answer"):
        answer = state.analysis.general_answer
    
    new_state = state.model_copy(update={
        "current_step": "general_response",
        "final_output": answer
    })
    
    return _update_step_history(
        new_state,
        "general_response",
        "SUCCESS",
        summary="일반 질의 응답 완료"
    )


# =============================================================================
# Agent 래퍼 함수 (Logging Wrapper)
# =============================================================================

@handle_node_error
def run_analyzer_node(state: PlanCraftState) -> PlanCraftState:
    """분석 Agent 실행 노드"""
    from agents.analyzer import run
    
    # Analyzer 실행
    new_state = run(state)
    
    # 상태 및 이력 업데이트
    return _update_step_history(
        new_state, 
        "analyze", 
        "SUCCESS", 
        summary=f"주제 분석: {new_state.analysis.topic if new_state.analysis else 'N/A'}"
    )

@handle_node_error
def run_structurer_node(state: PlanCraftState) -> PlanCraftState:
    """구조화 Agent 실행 노드"""
    from agents.structurer import run

    new_state = run(state)
    
    return _update_step_history(
        new_state, 
        "structure", 
        "SUCCESS", 
        summary=f"섹션 {len(new_state.structure.sections) if new_state.structure else 0}개 구조화"
    )

@handle_node_error
def run_writer_node(state: PlanCraftState) -> PlanCraftState:
    """작성 Agent 실행 노드"""
    from agents.writer import run

    new_state = run(state)
    
    # Draft 내용 요약
    draft_len = sum(len(s.content) for s in new_state.draft.sections) if new_state.draft else 0
    
    return _update_step_history(
        new_state, "write", "SUCCESS", summary=f"초안 작성 완료 ({draft_len}자)"
    )

@handle_node_error
def run_reviewer_node(state: PlanCraftState) -> PlanCraftState:
    """검토 Agent 실행 노드"""
    from agents.reviewer import run

    new_state = run(state)
    
    # Review 결과 요약
    verdict = new_state.review.verdict if new_state.review else "N/A"
    score = new_state.review.overall_score if new_state.review else 0
    return _update_step_history(
        new_state, "review", "SUCCESS", summary=f"심사 결과: {verdict} ({score}점)"
    )

@handle_node_error
def run_refiner_node(state: PlanCraftState) -> PlanCraftState:
    """개선 Agent 실행 노드"""
    from agents.refiner import run

    new_state = run(state)

    # 이력 업데이트 (성공 시 Refine Count는 Agent 내부에서 증가됨)
    return _update_step_history(
        new_state,
        "refine",
        "SUCCESS",
        summary=f"기획서 개선 완료 (Round {new_state.refine_count})"
    )

@handle_node_error
def run_formatter_node(state: PlanCraftState) -> PlanCraftState:
    """포맷팅 Agent 실행 노드"""
    # 현재 별도 Agent 없이 단순히 MarkDown 정리만 수행한다고 가정
    # 실제 구현이 있다면 import해서 사용

    new_state = state.model_copy(update={"current_step": "format"})

    # 예시: 파이널 아웃풋 확정
    if new_state.draft:
        final_md = "# " + (new_state.structure.title if new_state.structure else "기획서") + "\n\n"
        for sec in new_state.draft.sections:
            final_md += f"## {sec.name}\n\n{sec.content}\n\n"

        new_state = new_state.model_copy(update={"final_output": final_md})

    return _update_step_history(
        new_state, "format", "SUCCESS", summary="최종 포맷팅 완료"
    )


# =============================================================================
# 워크플로우 생성
# =============================================================================

def create_workflow() -> StateGraph:
    """PlanCraft 워크플로우 생성 (기본 버전)"""
    from graph.state import PlanCraftInput, PlanCraftOutput  # [NEW]
    
    # Pydantic 모델을 State로 사용하며, Input/Output 스키마를 명시합니다.
    workflow = StateGraph(PlanCraftState, input=PlanCraftInput, output=PlanCraftOutput)

    # 노드 등록 (래퍼 함수 사용)
    # [UPDATE] 컨텍스트 수집 단계 병렬화 (Sub-graph Node)
    from graph.subgraphs import run_context_subgraph
    workflow.add_node("context_gathering", run_context_subgraph)
    
    # workflow.add_node("retrieve", retrieve_context)  # [REMOVED]
    # workflow.add_node("fetch_web", fetch_web_context) # [REMOVED]
    
    workflow.add_node("analyze", run_analyzer_node)
    
    # [NEW] 분기 처리용 노드 등록
    workflow.add_node("option_pause", option_pause_node)
    workflow.add_node("general_response", general_response_node)
    
    workflow.add_node("structure", run_structurer_node)
    workflow.add_node("write", run_writer_node)
    workflow.add_node("review", run_reviewer_node)
    workflow.add_node("refine", run_refiner_node)
    workflow.add_node("format", run_formatter_node)

    # 엣지 정의
    # [UPDATE] 병렬 컨텍스트 수집 노드로 진입
    workflow.set_entry_point("context_gathering")
    workflow.add_edge("context_gathering", "analyze")
    # workflow.add_edge("retrieve", "fetch_web") # [REMOVED]
    # workflow.add_edge("fetch_web", "analyze") # [REMOVED]

    # [UPDATE] 조건부 분기 개선 (명시적 노드로 라우팅)
    workflow.add_conditional_edges(
        "analyze",
        should_ask_user,
        {
            "option_pause": "option_pause",
            "general_response": "general_response",
            "continue": "structure"
        }
    )
    
    # 분기 노드 후 처리 (Streamlit 앱 제어를 위해 END로 이동)
    workflow.add_edge("option_pause", END)
    workflow.add_edge("general_response", END)

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

    # [UPDATE] Input Schema 분리에 따른 입력 구성
    # PlanCraftInput 스키마에 정의된 필드만 전달하면 LangGraph가 내부 State로 자동 변환합니다.
    inputs = {
        "user_input": user_input,
        "file_content": file_content,
        "refine_count": refine_count,
        "previous_plan": previous_plan,
        "thread_id": thread_id
    }

    # 워크플로우 실행 (invoke는 dict 또는 BaseModel을 받음)
    # [NEW] Config에 thread_id 추가 (Checkpointer가 이를 식별)
    config = {"configurable": {"thread_id": thread_id}}
    
    if callbacks:
        config["callbacks"] = callbacks

    final_state = app.invoke(inputs, config=config)

    # UI 계층에서는 dict 처리가 되어 있으므로 변환하여 반환
    if hasattr(final_state, "model_dump"):
        return final_state.model_dump()
    return final_state
