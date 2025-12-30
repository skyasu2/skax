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

from enum import Enum
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from utils.checkpointer import get_checkpointer  # [NEW] Factory 패턴
from langchain_core.runnables import RunnableBranch  # [NEW] 분기 패턴
from graph.state import PlanCraftState
from utils.settings import settings

# [UPDATE] 로깅 핸들러 데코레이터
from functools import wraps


# =============================================================================
# 라우팅 키 상수 (Enum) - 문자열 하드코딩 방지
# =============================================================================

class RouteKey(str, Enum):
    """
    워크플로우 라우팅 키 상수

    문자열 하드코딩 대신 Enum 사용으로 타입 안전성 및 자동완성 지원.
    str 상속으로 add_conditional_edges에서 직접 사용 가능.
    """
    # Analyzer 분기
    CONTINUE = "continue"
    OPTION_PAUSE = "option_pause"
    GENERAL_RESPONSE = "general_response"

    # Reviewer 분기
    RESTART = "restart"
    REFINE = "refine"
    COMPLETE = "complete"
    DISCUSS = "discuss"
    SKIP_TO_REFINE = "skip_to_refine"

    # Refiner 분기
    RETRY = "retry"
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

def _update_step_history(state: PlanCraftState, step_name: str, status: str, summary: str = "", start_time: float = 0.0) -> PlanCraftState:
    """Step 실행 결과를 state의 history에 추가하고 로깅합니다."""
    # (기존 코드 생략...)
    
    # ... Helper 함수 구현 유지 ...
    from graph.state import update_state
    
    # 시간 측정
    import time
    if not start_time:  # 0.0 or None
        start_time = time.time() # fallback
        
    execution_time = f"{time.time() - start_time:.2f}s"
    
    # 로그 기록
    logger = get_file_logger()
    log_msg = f"[{step_name.upper()}] {status}"
    if summary:
        log_msg += f" - {summary}"
    logger.info(log_msg)
    
    # History 항목 생성
    history_item = {
        "step": step_name,
        "status": status,
        "summary": summary,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "execution_time": execution_time
    }
    
    # State 업데이트 (불변성 유지)
    current_history = state.get("step_history", []) or []
    new_history = current_history + [history_item]
    
    return update_state(
        state, 
        current_step=step_name,
        step_status=status,
        step_history=new_history,
        last_error=None if status == "SUCCESS" else state.get("last_error")
    )


# =============================================================================
# Condition Logic (라우팅 조건)
# =============================================================================

# =============================================================================
# Reviewer 라우팅 조건 함수 (RunnableBranch용)
# =============================================================================
#
# [RunnableBranch 분기 테이블]
# ┌────────────────────────┬──────────────────┬──────────────────────────────┐
# │ 조건 함수              │ 반환 액션        │ 설명                         │
# ├────────────────────────┼──────────────────┼──────────────────────────────┤
# │ _is_max_restart_reached│ refine           │ 무한 루프 방지 (2회 초과)    │
# │ _is_quality_fail       │ restart          │ 심각한 품질 문제 → 재분석    │
# │ _is_quality_pass       │ complete         │ 우수 품질 → 즉시 완료        │
# │ (default)              │ refine           │ 개선 필요 → Refiner          │
# └────────────────────────┴──────────────────┴──────────────────────────────┘
#
# [확장 방법] 새 조건 추가 시:
# 1. 조건 함수 정의: def _is_new_condition(state) -> bool
# 2. create_reviewer_routing_branch()에 튜플 추가: (_is_new_condition, action)
# =============================================================================

def _is_max_restart_reached(state: PlanCraftState) -> bool:
    """
    최대 복귀 횟수(2회) 도달 여부

    - True: Analyzer 복귀 횟수가 2회 이상 → 무한 루프 방지
    - False: 아직 복귀 가능
    """
    return state.get("restart_count", 0) >= 2


def _is_quality_fail(state: PlanCraftState) -> bool:
    """
    품질 실패 판정

    - True: score < 5 또는 verdict == "FAIL" → Analyzer로 복귀
    - False: 다음 조건 평가
    """
    review = state.get("review", {})
    score = review.get("overall_score", 5)
    verdict = review.get("verdict", "REVISE")
    return score < 5 or verdict == "FAIL"


def _is_quality_pass(state: PlanCraftState) -> bool:
    """
    품질 통과 판정

    - True: score >= 9 및 verdict == "PASS" → 즉시 Formatter
    - False: Refiner로 개선 필요
    """
    review = state.get("review", {})
    score = review.get("overall_score", 5)
    verdict = review.get("verdict", "REVISE")
    return score >= 9 and verdict == "PASS"


def create_reviewer_routing_branch() -> RunnableBranch:
    """
    Reviewer 결과에 따른 라우팅 분기 (RunnableBranch 패턴)

    분기 로직 (우선순위 순):
    1. restart_count >= 2 → refine (무한 루프 방지)
    2. score < 5 또는 FAIL → restart (Analyzer 복귀)
    3. score >= 9 및 PASS → complete (Formatter)
    4. default → refine (Refiner)

    확장 가능: 새로운 조건 추가 시 튜플만 추가하면 됨
    """
    from graph.state import update_state

    return RunnableBranch(
        # 조건 1: 최대 복귀 횟수 도달 → 강제 refine
        (_is_max_restart_reached, lambda s: update_state(s, routing_decision="refine")),
        # 조건 2: 품질 실패 → restart
        (_is_quality_fail, lambda s: update_state(s, routing_decision="restart")),
        # 조건 3: 품질 통과 → complete
        (_is_quality_pass, lambda s: update_state(s, routing_decision="complete")),
        # 기본값: refine
        lambda s: update_state(s, routing_decision="refine")
    )


def should_refine_or_restart(state: PlanCraftState) -> str:
    """
    Reviewer 결과에 따라 다음 단계 결정 (Multi-Agent 동적 라우팅)

    내부적으로 RunnableBranch 로직 사용, add_conditional_edges 호환 반환값 제공

    분기 로직:
    - score < 5 또는 FAIL → Analyzer로 복귀 (재분석)
    - score 5~8 또는 REVISE → Refiner (개선)
    - score ≥ 9 또는 PASS → Formatter (완료)

    안전장치:
    - restart_count >= 2 → 무한 복귀 방지
    """
    logger = get_file_logger()
    review = state.get("review", {})
    score = review.get("overall_score", 5)
    verdict = review.get("verdict", "REVISE")
    restart_count = state.get("restart_count", 0)

    # RunnableBranch 조건 평가 (우선순위 순)
    if _is_max_restart_reached(state):
        logger.info(f"[ROUTING] 최대 복귀 횟수 도달 ({restart_count}), Refiner로 진행")
        return RouteKey.REFINE

    if _is_quality_fail(state):
        logger.info(f"[ROUTING] 점수 낮음 ({score}점, {verdict}), Analyzer로 복귀")
        return RouteKey.RESTART

    if _is_quality_pass(state):
        logger.info(f"[ROUTING] 품질 우수 ({score}점, {verdict}), 바로 완료")
        return RouteKey.COMPLETE

    logger.info(f"[ROUTING] 개선 필요 ({score}점, {verdict}), Refiner로")
    return RouteKey.REFINE




# =============================================================================
# 노드 함수 정의 (모두 PlanCraftState TypedDict 사용)
# =============================================================================
#
# [Side-Effect 정책]
# ┌────────────────────────────────────────────────────────────────────────────┐
# │ 노드 유형          │ Side-Effect   │ 주의사항                              │
# ├────────────────────────────────────────────────────────────────────────────┤
# │ 일반 노드          │ LLM 호출 있음 │ 실패 시 재시도됨 (멱등성 권장)        │
# │ interrupt 노드     │ ⚠️ 중요       │ interrupt 전에 Side-Effect 금지!      │
# │                    │               │ Resume 시 노드 처음부터 재실행됨      │
# └────────────────────────────────────────────────────────────────────────────┘
#
# interrupt() 사용 노드 목록:
# - option_pause_node: 사용자 입력 대기 (interrupt 전 Side-Effect 없음)
#
# 안전한 패턴:
# 1. interrupt() 전: 순수 함수만 (payload 생성, 조건 검사)
# 2. interrupt() 후: Side-Effect 허용 (DB 저장, API 호출, 상태 업데이트)
#
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
    """
    조건부 웹 정보 수집 노드

    Side-Effect: 외부 웹 API 호출 (Tavily Search)
    - 실패 시 재시도 안전함 (조회 전용, 멱등성 보장)
    - 중복 호출 시 동일 결과 반환 (검색 결과 캐싱 없음)
    """
    import re
    from utils.config import Config
    from tools.mcp_client import fetch_url_sync, search_sync
    from tools.web_search import should_search_web
    from graph.state import update_state

    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context")
    web_contents = []
    web_urls = []
    web_sources = []  # [{"title": "...", "url": "..."}] 제목+URL 저장

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
                
                # [Optimization] 다중 쿼리 병렬 실행
                from concurrent.futures import ThreadPoolExecutor, as_completed
                
                def run_query(idx, q):
                    try:
                        return idx, q, search_sync(q)
                    except Exception as e:
                        return idx, q, {"success": False, "error": str(e)}

                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(run_query, i, q) for i, q in enumerate(queries)]
                    
                    # 순서 보장을 위해 인덱스로 정렬할 수 있도록 결과 수집
                    results = []
                    for future in as_completed(futures):
                        results.append(future.result())
                    
                    # 인덱스 순 정렬
                    results.sort(key=lambda x: x[0])
                    
                    for idx, q, search_result in results:
                        if search_result.get("success"):
                            formatted_result = ""
                            if "results" in search_result and isinstance(search_result["results"], list):
                                for res in search_result["results"][:3]:
                                    title = res.get("title", "제목 없음")
                                    url = res.get("url", "URL 없음")
                                    snippet = res.get("snippet", "")[:200]
                                    formatted_result += f"- [{title}]({url})\n  {snippet}\n"
                                    if url and url.startswith("http"):
                                        web_urls.append(url)
                                        # [NEW] 제목+URL 함께 저장 (중복 제거)
                                        if not any(s.get("url") == url for s in web_sources):
                                            web_sources.append({"title": title, "url": url})
                            
                            if not formatted_result and "formatted" in search_result:
                                formatted_result = search_result["formatted"]
                                
                            web_contents.append(f"[웹 검색 결과 {idx+1} - {q}]\n{formatted_result}")
                        else:
                            print(f"[WARN] 검색 실패 ({q}): {search_result.get('error')}")

        # 3. 상태 업데이트
        existing_context = state.get("web_context")
        existing_urls = state.get("web_urls") or []
        existing_sources = state.get("web_sources") or []

        new_context_str = "\n\n---\n\n".join(web_contents) if web_contents else None

        final_context = existing_context
        if new_context_str:
            final_context = f"{final_context}\n\n{new_context_str}" if final_context else new_context_str

        final_urls = list(dict.fromkeys(existing_urls + web_urls))

        # web_sources 병합 (중복 URL 제거)
        final_sources = existing_sources.copy()
        for src in web_sources:
            if not any(s.get("url") == src.get("url") for s in final_sources):
                final_sources.append(src)

        new_state = update_state(
            state,
            web_context=final_context,
            web_urls=final_urls,
            web_sources=final_sources,
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
    """
    Analyze 노드 이후 조건부 라우터.
    
    분기 조건:
        - "option_pause": 사용자에게 추가 정보를 요청해야 할 때 (need_more_info=True)
        - "general_response": 잡담/일반 질의일 때 (is_general_query=True)
        - "continue": 기획서 생성 파이프라인으로 진행할 때
    
    Returns:
        str: 다음 노드 이름 ("option_pause", "general_response", "continue")
    """
    if is_human_interrupt_required(state):
        return RouteKey.OPTION_PAUSE
    if is_general_query(state):
        return RouteKey.GENERAL_RESPONSE
    return RouteKey.CONTINUE


def is_human_interrupt_required(state: PlanCraftState) -> bool:
    """
    사용자에게 추가 정보를 요청해야 하는지 판단.
    
    Analyzer가 분석 결과에서 need_more_info=True를 설정한 경우 True.
    """
    return state.get("need_more_info") is True


def is_general_query(state: PlanCraftState) -> bool:
    """
    사용자 입력이 기획서 요청이 아닌 일반 질의인지 판단.
    
    Analyzer가 분석 결과에서 is_general_query=True를 설정한 경우 True.
    (예: "안녕하세요", "뭘 할 수 있어요?" 같은 질문)
    """
    analysis = state.get("analysis")
    if not analysis:
        return False
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
    """
    분석 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)
    - 멱등성: 동일 입력에 유사한 결과 (LLM 특성상 약간의 변동 있음)
    - 재시도 안전: 상태 변경 없이 분석 결과만 반환
    """
    from agents.analyzer import run
    from graph.state import update_state
    
    # [PHASE 1] Reviewer에서 복귀한 경우 restart_count 증가
    current_restart_count = state.get("restart_count", 0)
    has_review = state.get("review") is not None
    
    if has_review:
        # Reviewer를 거친 후 다시 Analyzer로 온 경우 = 재분석
        current_restart_count += 1
        print(f"[ROUTING] Analyzer 재진입 (restart_count: {current_restart_count})")
    
    new_state = run(state)
    
    # restart_count 업데이트
    new_state = update_state(new_state, restart_count=current_restart_count)
    
    analysis = new_state.get("analysis")
    topic = "N/A"
    if analysis:
        topic = analysis.get("topic") if isinstance(analysis, dict) else getattr(analysis, "topic", "N/A")
    
    return _update_step_history(
        new_state, 
        "analyze", 
        "SUCCESS", 
        summary=f"주제 분석: {topic}" + (f" (재분석 #{current_restart_count})" if has_review else "")
    )

@handle_node_error
def run_structurer_node(state: PlanCraftState) -> PlanCraftState:
    """
    구조화 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)
    - 기획서 목차/섹션 구조 설계
    - 재시도 안전: 구조만 생성, 외부 상태 변경 없음
    """
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
    """
    작성 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)
    - 섹션별 상세 콘텐츠 작성 (가장 오래 걸리는 단계)
    - 재시도 안전: 콘텐츠만 생성, 외부 상태 변경 없음
    """
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
    """
    검토 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)
    - 품질 평가 및 verdict 결정 (PASS/REVISE/FAIL)
    - 재시도 안전: 평가 결과만 반환, 외부 상태 변경 없음
    """
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
def run_discussion_node(state: PlanCraftState) -> PlanCraftState:
    """
    에이전트 간 대화 노드 (Reviewer ↔ Writer)

    Side-Effect: 다중 LLM 호출 (SubGraph 내부)
    - Reviewer가 피드백을 제시하고 Writer가 개선 계획을 설명
    - 최대 DISCUSSION_MAX_ROUNDS 라운드 진행
    - 재시도 안전: 대화 기록만 생성, 외부 상태 변경 없음
    """
    from graph.subgraphs import run_discussion_subgraph

    new_state = run_discussion_subgraph(state)
    round_count = new_state.get("discussion_round", 0)
    consensus = new_state.get("consensus_reached", False)

    return _update_step_history(
        new_state,
        "discussion",
        "SUCCESS",
        summary=f"에이전트 대화 {round_count}라운드, 합의: {'완료' if consensus else '미완료'}"
    )


@handle_node_error
def run_refiner_node(state: PlanCraftState) -> PlanCraftState:
    """
    개선 Agent 실행 노드 (Strategy Planner)

    Side-Effect: LLM 호출 (Azure OpenAI)
    - Reviewer 피드백 기반 개선 전략 수립
    - 재시도 안전: 전략만 생성, 외부 상태 변경 없음
    """
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
    """
    포맷팅 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)

    처리 단계:
    1. Draft → Final Output 변환 (마크다운 조합)
    2. 웹 출처 링크 추가 (참고 자료 섹션)
    3. Formatter Agent 호출 (chat_summary 생성)
    4. refine_count 리셋 (사용자 수정 기회 3회 부여)

    재시도 안전: 포맷팅만 수행, 외부 상태 변경 없음
    """
    from graph.state import update_state
    from agents.formatter import run as formatter_run

    # =========================================================================
    # 1단계: Draft -> Final Output 변환
    # =========================================================================
    draft = state.get("draft")
    structure = state.get("structure")
    final_md = ""

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

        # 웹 검색 출처 추가
        # [UPDATE] Writer가 생성한 참고 자료 섹션 제거 후 링크 포함된 섹션으로 교체
        import re
        web_sources = state.get("web_sources") or []
        web_urls = state.get("web_urls") or []
        web_context = state.get("web_context") or ""

        # Writer가 생성한 참고 자료 섹션 제거 (링크 없는 텍스트만 있는 경우)
        # 패턴: ## 참고 자료 또는 ## 참고자료 부터 다음 ## 또는 문서 끝까지
        reference_pattern = r'\n*#{1,2}\s*참고\s*자료.*?(?=\n#{1,2}\s|\Z)'
        final_md = re.sub(reference_pattern, '', final_md, flags=re.DOTALL)

        # 웹 소스가 있으면 링크 포함된 참고 자료 섹션 추가
        if web_sources:
            final_md += "---\n\n## 📚 참고 자료\n\n"
            final_md += "> 본 기획서 작성 시 다음 자료를 참고하였습니다.\n\n"
            for i, source in enumerate(web_sources, 1):
                title = source.get("title", "")
                url = source.get("url", "")
                # 제목이 비어있거나 URL과 동일한 경우 도메인명 추출
                if not title or title == url:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    title = parsed.netloc.replace("www.", "") if parsed.netloc else "출처"
                final_md += f"{i}. [{title}]({url})\n"
            final_md += "\n"
        elif web_urls:
            # Fallback: URL만 있는 경우 도메인명 추출
            final_md += "---\n\n## 📚 참고 자료\n\n"
            final_md += "> 본 기획서 작성 시 다음 자료를 참고하였습니다.\n\n"
            for i, url in enumerate(web_urls, 1):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc.replace("www.", "") if parsed.netloc else "출처"
                final_md += f"{i}. [{domain}]({url})\n"
            final_md += "\n"
        elif web_context and "웹 검색 결과" in web_context:
            final_md += "---\n\n## 📚 참고 자료\n\n"
            final_md += "> 본 기획서는 웹 검색을 통해 수집한 최신 정보를 반영하였습니다.\n\n"

    # =========================================================================
    # 2단계: Formatter Agent 호출 (chat_summary 생성 + refine_count=0 리셋)
    # =========================================================================
    state_with_output = update_state(state, final_output=final_md, current_step="format")
    new_state = formatter_run(state_with_output)

    return _update_step_history(
        new_state, "format", "SUCCESS", summary="최종 포맷팅 및 교정 완료"
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
    휴먼 인터럽트 처리 노드 (LangGraph 공식 Best Practice 적용)
    
    LangGraph Human Interrupt 필수 요소:
    1. interrupt() 함수로 Pause
    2. Command(resume=...) 로 Resume
    3. checkpointer로 상태 저장 (compile 시 설정됨)
    4. thread_id로 세션 관리
    5. interrupt 전에는 side effect 없음 (비효과적 코드만)
    
    주의사항:
    - interrupt 전에 외부 API 호출, DB 쓰기 금지 (Resume 시 중복 실행됨)
    - interrupt 이후에 side effect 배치
    """
    from graph.interrupt_utils import create_option_interrupt, handle_user_response
    
    # =========================================================================
    # [BEFORE INTERRUPT] 비효과적 코드만 (side effect 없음)
    # =========================================================================
    # 1. 인터럽트 페이로드 생성 (순수 함수, 외부 호출 없음)
    payload = create_option_interrupt(state)
    payload["type"] = "option_selector"
    
    # =========================================================================
    # [INTERRUPT] 실행 중단 - 사용자 응답 대기 (무한 루프로 검증)
    # =========================================================================
    user_response = None
    
    # [NEW] Input Validation Loop - Code Reviewer's Advice
    MAX_RETRIES = settings.HITL_MAX_RETRIES
    retry_count = 0
    
    # [CRITICAL WARNING for Maintainers]
    # interrupt() 호출 이전에는 절대 LLM 호출, DB 저장 등 Side Effect가 있는 코드를 배치하지 마십시오.
    # 재개(Resume) 시 이 노드는 처음부터 다시 실행되므로, Side Effect가 중복 실행(Duplicate Execution)될 수 있습니다.
    # (LangGraph Best Practice: Side Effect는 항상 interrupt 이후 혹은 별도 노드에서 처리)

    # [NEW] Input Validation Loop with Safety Limit
    while retry_count < MAX_RETRIES:
        # [NEW] 재시도 시 사용자에게 에러 피드백 제공
        if retry_count > 0:
            payload["error"] = "⚠️ 입력값이 비어있습니다. 다시 선택해주세요."
            # [OPTION] 질문 업데이트 (선택 사항)
            # payload["question"] = f"[재입력 요청] {payload['question']}"
            
        # interrupt() 호출 시 실행 중단 -> Resume 시 값 반환
        user_response = interrupt(payload)
        
        # 유효성 검사: 값이 존재해야 함 (None, 빈 문자열 등 방지)
        if user_response:
            # [LOG] 사용자 응답 기록
            get_file_logger().info(f"[HITL] User Response: {user_response}")
            print(f"[Human-Node] Valid Input Received: {user_response}")
            break
            
        retry_count += 1
        print(f"[Human-Node] Invalid Input (Empty). Retry {retry_count}/{MAX_RETRIES}")
        
    # 최대 재시도 초과 시 안전 조치
    if not user_response:
        msg = f"[HITL] Max retries reached ({MAX_RETRIES}). Forcing default action (continue)."
        print(msg)
        get_file_logger().warning(msg)
        user_response = {"action": "continue", "value": "default_fallback"}

    
    
    # =========================================================================
    # [AFTER INTERRUPT] Resume 후 실행되는 코드
    # =========================================================================
    # user_response는 Resume 시 Command(resume=...)로 전달된 값
    
    # 3. 사용자 응답으로 상태 업데이트
    updated_state = handle_user_response(state, user_response)
    
    return Command(
        update=updated_state,
        goto="analyze"  # 새 정보로 다시 분석
    )


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
    
    workflow.add_node("analyze", run_analyzer_node)
    
    # [NEW] 분기 처리용 노드 등록
    workflow.add_node("option_pause", option_pause_node)
    workflow.add_node("general_response", general_response_node)
    
    workflow.add_node("structure", run_structurer_node)
    
    workflow.add_node("write", run_writer_node)
    workflow.add_node("review", run_reviewer_node)
    workflow.add_node("discussion", run_discussion_node)  # [NEW] 에이전트 간 대화
    workflow.add_node("refine", run_refiner_node)
    workflow.add_node("format", run_formatter_node)

    # 엣지 정의
    # [UPDATE] 병렬 컨텍스트 수집 노드로 진입
    workflow.set_entry_point("context_gathering")
    workflow.add_edge("context_gathering", "analyze")

    # [UPDATE] 조건부 분기 개선 (명시적 노드로 라우팅)
    workflow.add_conditional_edges(
        "analyze",
        should_ask_user,
        {
            RouteKey.OPTION_PAUSE: "option_pause",
            RouteKey.GENERAL_RESPONSE: "general_response",
            RouteKey.CONTINUE: "structure"
        }
    )
    
    # 분기 노드 후 처리 (Streamlit 앱 제어를 위해 END로 이동)
    workflow.add_edge("option_pause", END)
    workflow.add_edge("general_response", END)


    # [UPDATE] Structure -> Write (Direct connection)
    workflow.add_edge("structure", "write")
    
    # write 노드는 structure에서 직접 연결됨
    workflow.add_edge("write", "review")

    # [UPDATE] Review 후 스마트 분기: 점수 기반 최적화 라우팅
    def should_discuss_or_complete(state: PlanCraftState) -> str:
        """
        Review 후 Discussion 필요 여부 결정 (성능 최적화)

        라우팅 로직:
        - score >= 9 (PASS): 바로 완료 → format
        - score >= DISCUSSION_SKIP_THRESHOLD (7): Discussion 스킵 → refine
        - score < 7: Discussion 필요 → discuss
        - score < 5 (FAIL): Analyzer 복귀 → restart
        """
        logger = get_file_logger()
        review = state.get("review", {})
        score = review.get("overall_score", 5)
        verdict = review.get("verdict", "REVISE")
        skip_threshold = settings.DISCUSSION_SKIP_THRESHOLD

        # PASS 판정: 바로 완료
        if score >= 9 and verdict == "PASS":
            logger.info(f"[ROUTING] 품질 우수 ({score}점), 바로 완료")
            return RouteKey.COMPLETE

        # FAIL 판정: Analyzer 복귀
        if score < 5 or verdict == "FAIL":
            logger.info(f"[ROUTING] 품질 부족 ({score}점), Analyzer 복귀")
            return RouteKey.RESTART

        # 중간 점수 (7-8): Discussion 스킵하고 바로 Refine
        if score >= skip_threshold:
            logger.info(f"[ROUTING] 중간 품질 ({score}점 >= {skip_threshold}), Discussion 스킵 → Refine")
            return RouteKey.SKIP_TO_REFINE

        # 낮은 점수 (5-6): Discussion 필요
        logger.info(f"[ROUTING] 개선 필요 ({score}점), Discussion 진행")
        return RouteKey.DISCUSS

    workflow.add_conditional_edges(
        "review",
        should_discuss_or_complete,
        {
            RouteKey.DISCUSS: "discussion",         # 5-6점: 에이전트 간 대화
            RouteKey.SKIP_TO_REFINE: "refine",      # 7-8점: Discussion 스킵
            RouteKey.COMPLETE: "format",            # 9점+: 바로 완료
            RouteKey.RESTART: "analyze"             # 5점-: Analyzer 복귀
        }
    )

    # [UPDATE] Discussion 후 항상 Refine으로 진행 (단순화)
    # Discussion은 5-6점에서만 실행되므로 합의 후 항상 개선 필요
    workflow.add_edge("discussion", "refine")

    # [UPDATE] Refiner 조건부 엣지 - REVISE 판정 시 재작성 루프
    def should_refine_again(state: PlanCraftState) -> str:
        """
        Refiner 후 다음 단계 결정 (Graceful End-of-Loop 패턴 적용)

        안전 탈출 조건 (OR 연산):
        1. refined=False: 개선 불필요 (PASS 판정)
        2. refine_count >= MAX_REFINE_LOOPS: 최대 루프 도달
        3. remaining_steps <= MIN_REMAINING_STEPS: 남은 스텝 부족
        
        위 조건 중 하나라도 충족하면 format으로 진행하여 완료합니다.
        """
        refined = state.get("refined", False)
        refine_count = state.get("refine_count", 0)
        remaining_steps = state.get("remaining_steps", 100)  # 기본값 충분히 크게
        
        # [NEW] Graceful End-of-Loop: 남은 스텝이 부족하면 안전하게 종료
        if remaining_steps <= settings.MIN_REMAINING_STEPS:
            print(f"[WARN] 남은 스텝 부족 ({remaining_steps}), 루프 종료")
            return RouteKey.COMPLETE

        # 최대 루프 횟수 초과
        if refine_count >= settings.MAX_REFINE_LOOPS:
            print(f"[WARN] 최대 루프 도달 ({refine_count}), 루프 종료")
            return RouteKey.COMPLETE

        # 개선 필요 여부
        if refined:
            return RouteKey.RETRY
        return RouteKey.COMPLETE

    workflow.add_conditional_edges(
        "refine",
        should_refine_again,
        {
            RouteKey.RETRY: "structure",      # 재작성 루프
            RouteKey.COMPLETE: "format"       # 완료
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
    # 체크포인터 설정 (Factory 사용)
    from utils.checkpointer import get_checkpointer
    checkpointer = get_checkpointer()
    
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
