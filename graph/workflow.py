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
            │   context    │  <- RAG + MCP (병렬 컨텍스트 수집)
            │  gathering   │
            └──────┬───────┘
                   │
            ┌──────▼───────┐      need_more_info=True     ┌─────────┐
            │   analyze    │ ───────────────────────────▶ │   END   │
            └──────┬───────┘      (질문 생성 및 중단)      └─────────┘
                   │
                   │ need_more_info=False (자동 진행)
                   ▼
       ┌──────────────────────────────────────────┐
       │         Refinement Loop (최대 3회)        │
       │  ┌──────▼───────┐                        │
       │  │  structure   │  <- 기획서 목차/구조 설계│
       │  └──────┬───────┘                        │
       │         │                                │
       │  ┌──────▼───────┐                        │
       │  │    write     │  <- 섹션별 내용 작성    │
       │  └──────┬───────┘                        │
       │         │                                │
       │  ┌──────▼───────┐                        │
       │  │    review    │  <- PASS/REVISE/FAIL   │
       │  └──────┬───────┘                        │
       │         │                                │
       │  ┌──────▼───────┐    refined=True        │
       │  │    refine    │ ───────────────────────┘
       │  └──────┬───────┘    (재작성 필요)
       └─────────│────────────────────────────────┘
                 │ refined=False (완료)
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
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver  # 체크포인터
from langchain_core.runnables import RunnableBranch  # [NEW] 분기 패턴
from graph.state import PlanCraftState
from agents import analyzer, structurer, writer, reviewer, refiner, formatter
from utils.config import Config
from utils.file_logger import get_file_logger
from utils.error_handler import handle_node_error
from graph.interrupt_utils import create_option_interrupt, handle_user_response

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
    from graph.state import update_state
    
    # 1. History Item 생성
    history_item = {
        "step": step,
        "status": status,
        "summary": summary,
        "error": error,
        "timestamp": datetime.now().isoformat()
    }
    
    # 2. Immutable Update (List append) - TypedDict dict 접근
    current_history = state.get("step_history", []) or []
    new_history = list(current_history) + [history_item]
    
    # 3. State 업데이트 - TypedDict 방식
    updated_state = update_state(
        state,
        step_history=new_history,
        current_step=step,
        step_status=status,
        last_error=error
    )
    
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
    from graph.state import update_state

    # Retriever 초기화 (상위 3개 문서 검색)
    retriever = Retriever(k=3)

    # 사용자 입력으로 관련 문서 검색
    user_input = state["user_input"]
    context = retriever.get_formatted_context(user_input)

    new_state = update_state(state, rag_context=context, current_step="retrieve")

    # [LOG] 실행 결과 로깅 및 히스토리 업데이트
    status = "SUCCESS"
    rag_context = new_state.get("rag_context")
    summary = f"검색된 문서: {len(rag_context.split('---')) if rag_context else 0}건"
    
    return _update_step_history(new_state, "retrieve", status, summary)


# ... (상단 생략)

@handle_node_error
def fetch_web_context(state: PlanCraftState) -> PlanCraftState:
    """조건부 웹 정보 수집 노드"""
    import re
    from utils.config import Config
    from tools.mcp_client import fetch_url_sync, search_sync
    from tools.web_search import should_search_web
    from graph.state import update_state

    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context")
    web_contents = []
    web_urls = []

    try:
        # 1. URL이 직접 제공된 경우
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, user_input)

        if urls:
            for url in urls[:3]:
                try:
                    content = fetch_url_sync(url, max_length=3000)
                    if content and not content.startswith("[웹 조회 실패"):
                        web_contents.append(f"[URL 참조: {url}]\n{content}")
                        web_urls.append(url)
                except Exception as e:
                    print(f"[WARN] URL 조회 실패 ({url}): {e}")
        # 2. URL이 없으면 조건부 웹 검색
        else:
            decision = should_search_web(user_input, rag_context if rag_context else "")
            if decision["should_search"]:
                base_query = decision["search_query"]
                queries = [base_query]
                if "트렌드" in base_query:
                    queries.append(base_query.replace("트렌드", "시장 규모 통계"))
                else:
                    queries.append(f"{base_query} 시장 규모 및 경쟁사")
                
                for i, q in enumerate(queries):
                    search_result = search_sync(q)
                    if search_result["success"]:
                        # ... (결과 포맷팅 로직 유지) ...
                        formatted_result = ""
                        if "results" in search_result and isinstance(search_result["results"], list):
                            for idx, res in enumerate(search_result["results"][:3]):
                                title = res.get("title", "제목 없음")
                                url = res.get("url", "URL 없음")
                                snippet = res.get("snippet", "")[:200]
                                formatted_result += f"- [{title}]({url})\n  {snippet}\n"
                        if not formatted_result and "formatted" in search_result:
                            formatted_result = search_result["formatted"]
                            
                        web_contents.append(f"[웹 검색 결과 {i+1} - {q}]\n{formatted_result}")
                    else:
                        print(f"[WARN] 검색 실패 ({q}): {search_result.get('error')}")

        # 3. 상태 업데이트
        existing_context = state.get("web_context")
        existing_urls = state.get("web_urls") or []
        
        new_context_str = "\n\n---\n\n".join(web_contents) if web_contents else None
        
        final_context = existing_context
        if new_context_str:
            final_context = f"{final_context}\n\n{new_context_str}" if final_context else new_context_str
                
        final_urls = list(dict.fromkeys(existing_urls + web_urls))
        
        new_state = update_state(
            state,
            web_context=final_context,
            web_urls=final_urls,
            current_step="fetch_web"
        )

    except Exception as e:
        print(f"[WARN] 웹 조회 단계 오류: {e}")
        new_state = update_state(
            state,
            web_context=None,
            web_urls=[],
            error=f"웹 조회 오류: {str(e)}"
        )

    status = "FAILED" if new_state.get("error") else "SUCCESS"
    url_count = len(new_state.get("web_urls") or [])
    summary = f"웹 정보 수집: {url_count}개 URL 참조"
    
    return _update_step_history(new_state, "fetch_web", status, summary, new_state.get("error"))


def should_ask_user(state: PlanCraftState) -> str:
    """조건부 라우터"""
    if is_human_interrupt_required(state):
        return "option_pause"
    if is_general_query(state):
        return "general_response"
    return "continue"


def is_human_interrupt_required(state: PlanCraftState) -> bool:
    return state.get("need_more_info") is True


def is_general_query(state: PlanCraftState) -> bool:
    # analysis는 dict일 수도 있음
    analysis = state.get("analysis")
    if not analysis:
        return False
    # analysis가 dict면 .get, 객체면 getattr
    if isinstance(analysis, dict):
        return analysis.get("is_general_query", False)
    return getattr(analysis, "is_general_query", False)

# ... (중략) ...

def create_routing_branch():
    """RunnableBranch 분기 (TypedDict 호환)"""
    from graph.state import update_state
    return RunnableBranch(
        (
            is_human_interrupt_required,
            lambda state: update_state(state, routing_decision="ask_user")
        ),
        (
            is_general_query,
            lambda state: update_state(state, routing_decision="general_response")
        ),
        lambda state: update_state(state, routing_decision="continue")
    )

# ... (option_pause_node, general_response_node 생략, 아래에서 처리) ...

def general_response_node(state: PlanCraftState) -> PlanCraftState:
    """일반 질의 응답 노드"""
    from graph.state import update_state
    
    answer = "일반 질의에 대한 응답입니다."
    analysis = state.get("analysis")
    
    if analysis:
         if isinstance(analysis, dict):
             answer = analysis.get("general_answer", answer)
         else:
             answer = getattr(analysis, "general_answer", answer)
    
    new_state = update_state(
        state,
        current_step="general_response",
        final_output=answer
    )
    
    return _update_step_history(
        new_state,
        "general_response",
        "SUCCESS",
        summary="일반 질의 응답 완료"
    )

# =============================================================================
# Agent 래퍼 함수 (TypedDict 호환)
# =============================================================================

@handle_node_error
def run_analyzer_node(state: PlanCraftState) -> PlanCraftState:
    """분석 Agent 실행 노드"""
    from agents.analyzer import run
    
    new_state = run(state)
    analysis = new_state.get("analysis")
    topic = "N/A"
    if analysis:
        topic = analysis.get("topic") if isinstance(analysis, dict) else getattr(analysis, "topic", "N/A")
    
    return _update_step_history(
        new_state, 
        "analyze", 
        "SUCCESS", 
        summary=f"주제 분석: {topic}"
    )

@handle_node_error
def run_structurer_node(state: PlanCraftState) -> PlanCraftState:
    """구조화 Agent 실행 노드"""
    from agents.structurer import run

    new_state = run(state)
    structure = new_state.get("structure")
    count = 0
    if structure:
        sections = structure.get("sections") if isinstance(structure, dict) else getattr(structure, "sections", [])
        count = len(sections) if sections else 0
    
    return _update_step_history(
        new_state, 
        "structure", 
        "SUCCESS", 
        summary=f"섹션 {count}개 구조화"
    )

@handle_node_error
def run_writer_node(state: PlanCraftState) -> PlanCraftState:
    """작성 Agent 실행 노드"""
    from agents.writer import run

    new_state = run(state)
    draft = new_state.get("draft")
    draft_len = 0
    if draft:
        sections = draft.get("sections") if isinstance(draft, dict) else getattr(draft, "sections", [])
        if sections:
             # SectionContent 객체 or dict
             draft_len = sum(len(s.get("content", "") if isinstance(s, dict) else s.content) for s in sections)
    
    return _update_step_history(
        new_state, "write", "SUCCESS", summary=f"초안 작성 완료 ({draft_len}자)"
    )

@handle_node_error
def run_reviewer_node(state: PlanCraftState) -> PlanCraftState:
    """검토 Agent 실행 노드"""
    from agents.reviewer import run

    new_state = run(state)
    review = new_state.get("review")
    verdict = "N/A"
    score = 0
    if review:
        if isinstance(review, dict):
            verdict = review.get("verdict", "N/A")
            score = review.get("overall_score", 0)
        else:
            verdict = getattr(review, "verdict", "N/A")
            score = getattr(review, "overall_score", 0)

    return _update_step_history(
        new_state, "review", "SUCCESS", summary=f"심사 결과: {verdict} ({score}점)"
    )

@handle_node_error
def run_refiner_node(state: PlanCraftState) -> PlanCraftState:
    """개선 Agent 실행 노드"""
    from agents.refiner import run

    new_state = run(state)
    refine_count = new_state.get("refine_count", 0)

    return _update_step_history(
        new_state,
        "refine",
        "SUCCESS",
        summary=f"기획서 개선 완료 (Round {refine_count})"
    )

@handle_node_error
def run_formatter_node(state: PlanCraftState) -> PlanCraftState:
    """포맷팅 Agent 실행 노드"""
    from graph.state import update_state

    new_state = update_state(state, current_step="format")

    # Draft -> Final Output
    draft = new_state.get("draft")
    structure = new_state.get("structure")
    
    if draft:
        # Title 추출
        title = "기획서"
        if structure:
            title = structure.get("title") if isinstance(structure, dict) else getattr(structure, "title", "기획서")
        
        final_md = f"# {title}\n\n"
        
        # Sections 추출
        sections = draft.get("sections") if isinstance(draft, dict) else getattr(draft, "sections", [])
        
        for sec in sections:
            if isinstance(sec, dict):
                name = sec.get("name", "")
                content = sec.get("content", "")
            else:
                name = sec.name
                content = sec.content
            final_md += f"## {name}\n\n{content}\n\n"

        new_state = update_state(new_state, final_output=final_md)

    return _update_step_history(
        new_state, "format", "SUCCESS", summary="최종 포맷팅 완료"
    )


# =============================================================================
# 휴먼 인터럽트 노드 (option_pause_node)
# =============================================================================

try:
    from langgraph.types import interrupt, Command
except ImportError:
    # LangGraph 호환성 Mock
    def interrupt(value): return None
    class Command:
        def __init__(self, update=None, goto=None):
            self.update = update
            self.goto = goto


def option_pause_node(state: PlanCraftState) -> Command:
    """
    휴먼 인터럽트 처리 노드 (LangGraph 공식 패턴 적용)
    
    이 노드는 실행을 일시 중단하고 사용자 입력을 기다립니다.
    """
    from graph.interrupt_utils import create_option_interrupt, handle_user_response
    
    # 1. 인터럽트 페이로드 생성
    payload = create_option_interrupt(state)
    payload["type"] = "option_selector"
    
    # 2. 실행 중단 및 사용자 응답 대기
    try:
        user_response = interrupt(payload)
    except Exception:
        user_response = None
    
    # 3. 사용자 응답 처리 (Resume 후)
    if user_response:
        new_state = handle_user_response(state, user_response)
        
        # 4. 다음 단계로 이동 (Command 반환)
        # analyze 단계로 돌아가서 새로운 정보를 바탕으로 다시 분석
        return Command(
            update=new_state,
            goto="analyze" 
        )
    
    # interrupt가 지원되지 않는 경우 (Fallback)
    return Command(goto="analyze")


# =============================================================================
# 워크플로우 생성
# =============================================================================

def create_workflow() -> StateGraph:
    """PlanCraft 워크플로우 생성 (기본 버전)"""
    from graph.state import PlanCraftInput, PlanCraftOutput

    # LangGraph V0.5+ 호환: input_schema/output_schema 사용
    workflow = StateGraph(PlanCraftState, input_schema=PlanCraftInput, output_schema=PlanCraftOutput)

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

    # [UPDATE] Refiner 조건부 엣지 - REVISE 판정 시 재작성 루프
    def should_refine_again(state: PlanCraftState) -> str:
        """
        Refiner 후 다음 단계 결정

        - refined=True & refine_count < 3: 재작성 (structure로 회귀)
        - 그 외: 완료 (format으로 진행)
        """
        if state.get("refined") and state.get("refine_count", 0) < 3:
            return "retry"
        return "complete"

    workflow.add_conditional_edges(
        "refine",
        should_refine_again,
        {
            "retry": "structure",   # 재작성 루프
            "complete": "format"    # 완료
        }
    )

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
        if state.get("need_more_info"):
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
    thread_id: str = "default_thread",
    resume_command: dict = None  # [NEW] 재개를 위한 커맨드 데이터
) -> dict:
    """
    PlanCraft 워크플로우 실행 엔트리포인트
    
    Args:
        resume_command: 인터럽트 후 재개를 위한 데이터 (Command resume)
    """
    from graph.state import create_initial_state
    from langgraph.types import Command

    # [UPDATE] Input Schema 분리에 따른 입력 구성
    inputs = None
    if not resume_command:
        # 처음 시작할 때만 입력 구성
        inputs = {
            "user_input": user_input,
            "file_content": file_content,
            "refine_count": refine_count,
            "previous_plan": previous_plan,
            "thread_id": thread_id
        }

    # 워크플로우 실행설정
    config = {"configurable": {"thread_id": thread_id}}
    if callbacks:
        config["callbacks"] = callbacks

    # [UPDATE] 실행 로직 분기 (일반 실행 vs Resume 실행)
    if resume_command:
        # Resume 실행: Command 객체 전달
        # resume_command는 {"resume": ...} 형태여야 함
        input_data = Command(resume=resume_command.get("resume"))
    else:
        # 일반 실행
        input_data = inputs

    # 실행 (인터럽트 발생 시 중단됨)
    # invoke는 최종 state를 반환하지만, 중간에 멈추면 멈춘 시점의 state 반환
    final_state = app.invoke(input_data, config=config)

    # [NEW] 인터럽트 상태 확인
    snapshot = app.get_state(config)
    
    interrupt_payload = None
    if snapshot.next and snapshot.tasks:
        # 다음 단계가 있는데 멈췄다면 인터럽트일 가능성 확인
        # (LangGraph 최신 버전은 snapshot.tasks[0].interrupts에 정보가 있음)
        if hasattr(snapshot.tasks[0], "interrupts") and snapshot.tasks[0].interrupts:
            interrupt_payload = snapshot.tasks[0].interrupts[0].value
            
    # 결과 반환 준비
    result = {}
    
    # State 객체를 dict로 변환
    if hasattr(final_state, "model_dump"):
        result = final_state.model_dump()
    elif isinstance(final_state, dict):
        result = final_state
        
    # 인터럽트 정보 추가
    if interrupt_payload:
        result["__interrupt__"] = interrupt_payload
        
    return result
