"""
PlanCraft Agent - LangGraph 워크플로우 정의

Multi-Agent 파이프라인을 LangGraph StateGraph로 정의합니다.
각 Agent는 노드로 등록되며, 조건부 엣지를 통해 흐름을 제어합니다.

[CRITICAL SAFETY WARNING: Subgraph & Interrupt]
서브그래프(Subgraph) 또는 워크플로우 내에서 `interrupt`가 발생하면,
Resume 시 해당 인터럽트가 포함된 **가장 상위 그래프(Supergraph)의 노드부터 처음부터 재실행**될 수 있습니다.

**개발자 준수 사항:**
1. Side-Effect 분리: DB 쓰기, 외부 API 호출(과금), 이메일 발송 등은 반드시 `interrupt()` 호출 **이후**에 배치하세요.
2. Idempotency(멱등성): 노드는 여러 번 실행되어도 결과가 동일하도록 설계해야 합니다.
3. Resume Matching: `interrupt` 호출 순서나 개수는 동적으로 변경되면 안 됩니다. (Index 기반 매칭)

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
from typing import Literal, Union
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from utils.checkpointer import get_checkpointer  # [NEW] Factory 패턴
from langchain_core.runnables import RunnableBranch  # [NEW] 분기 패턴
from graph.state import PlanCraftState
from utils.settings import settings, QualityThresholds


# =============================================================================
# Command[Literal[...]] 타입 정의 (LangGraph Best Practice)
# =============================================================================
# 노드 함수의 반환 타입을 명시하여:
# 1. 정적 타입 검사로 라우팅 오류 조기 발견
# 2. IDE 자동완성 및 타입 힌트 지원
# 3. 워크플로우 문서화 자동화
# =============================================================================

# Analyzer 분기 후 가능한 목적지
AnalyzerRoutes = Literal["option_pause", "general_response", "structure"]

# Reviewer 분기 후 가능한 목적지
ReviewerRoutes = Literal["discussion", "refine", "format", "analyze"]

# Refiner 분기 후 가능한 목적지
RefinerRoutes = Literal["structure", "format"]

# option_pause_node의 Command 반환 타입
OptionPauseCommand = Command[Literal["analyze"]]

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
from utils.tracing import trace_node
from utils.error_handler import handle_node_error
from utils.decorators import require_state_keys
from utils.file_logger import get_file_logger
from graph.interrupt_utils import create_option_interrupt, handle_user_response

# [REFACTOR] Extracted Nodes
from graph.nodes.analyzer_node import run_analyzer_node
from graph.nodes.fetch_web import fetch_web_context
from graph.nodes.structurer_node import run_structurer_node
from graph.nodes.writer_node import run_writer_node
from graph.nodes.reviewer_node import run_reviewer_node
from graph.nodes.refiner_node import run_refiner_node
from graph.nodes.formatter_node import run_formatter_node
from graph.nodes.discussion_node import run_discussion_node
from graph.nodes.common import update_step_history
from graph.nodes.hitl_node import option_pause_node
from graph.nodes.utility_nodes import general_response_node

# =============================================================================
# LangSmith 트레이싱 활성화 (Observability)
# =============================================================================
Config.setup_langsmith()


# =============================================================================
# Helper: 실행 이력 기록 및 로깅 통합
# =============================================================================




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
    최대 복귀 횟수 도달 여부

    - True: Analyzer 복귀 횟수가 MAX_RESTART_COUNT 이상 → 무한 루프 방지
    - False: 아직 복귀 가능
    """
    return state.get("restart_count", 0) >= QualityThresholds.MAX_RESTART_COUNT


def _is_quality_fail(state: PlanCraftState) -> bool:
    """
    품질 실패 판정

    - True: score < SCORE_FAIL 또는 verdict == "FAIL" → Analyzer로 복귀
    - False: 다음 조건 평가
    """
    review = state.get("review", {})
    score = review.get("overall_score", QualityThresholds.FALLBACK_SCORE)
    verdict = review.get("verdict", "REVISE")
    return QualityThresholds.is_fail(score) or verdict == "FAIL"


def _is_quality_pass(state: PlanCraftState) -> bool:
    """
    품질 통과 판정

    - True: score >= SCORE_PASS 및 verdict == "PASS" → 즉시 Formatter
    - False: Refiner로 개선 필요
    """
    review = state.get("review", {})
    score = review.get("overall_score", QualityThresholds.FALLBACK_SCORE)
    verdict = review.get("verdict", "REVISE")
    return QualityThresholds.is_pass(score) and verdict == "PASS"


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


def should_refine_or_restart(state: PlanCraftState) -> ReviewerRoutes:
    """
    Reviewer 결과에 따라 다음 단계 결정 (Multi-Agent 동적 라우팅)

    Return Type: ReviewerRoutes = Literal["discussion", "refine", "format", "analyze"]

    내부적으로 RunnableBranch 로직 사용, add_conditional_edges 호환 반환값 제공

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                         판정표 (Decision Table)                         │
    ├──────────────┬──────────────┬─────────────────┬────────────────────────┤
    │ 조건         │ 점수 범위    │ 반환값          │ 다음 노드              │
    ├──────────────┼──────────────┼─────────────────┼────────────────────────┤
    │ 최대 복귀    │ restart >= 2 │ RouteKey.REFINE │ refine (무한루프 방지) │
    │ 품질 실패    │ score < 5    │ RouteKey.RESTART│ analyze (재분석)       │
    │ 품질 통과    │ score >= 9   │ RouteKey.COMPLETE│ format (완료)         │
    │ 개선 필요    │ 5 <= s < 9   │ RouteKey.REFINE │ refine (개선)          │
    └──────────────┴──────────────┴─────────────────┴────────────────────────┘

    Args:
        state: 현재 워크플로우 상태 (review 필드 필요)

    Returns:
        ReviewerRoutes: 다음 노드를 결정하는 라우팅 키 (Literal 타입)
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

@trace_node("context", tags=["rag", "retrieval"])
@handle_node_error
def retrieve_context(state: PlanCraftState) -> PlanCraftState:
    """
    RAG 검색 노드 (Advanced RAG Pipeline)

    프리셋에 따라 다양한 고급 RAG 기능을 활성화합니다:
    - quality 모드: Reranking + Multi-Query + Query Expansion + Context Reorder
    - balanced 모드: Multi-Query + Query Expansion
    - fast 모드: 기본 MMR 검색만

    LangSmith: run_name="📚 컨텍스트 수집", tags=["rag", "retrieval"]
    """
    import time
    start_time = time.time()
    
    from rag.retriever import Retriever
    from graph.state import update_state
    from utils.settings import get_preset

    # 프리셋에서 Advanced RAG 설정 로드
    preset_key = state.get("generation_preset", "balanced")
    preset = get_preset(preset_key)

    # Retriever 초기화 (프리셋 기반 고급 기능 활성화)
    retriever = Retriever(
        k=3,
        use_reranker=getattr(preset, 'use_reranker', False),
        use_multi_query=getattr(preset, 'use_multi_query', False),
        use_query_expansion=getattr(preset, 'use_query_expansion', False),
        use_context_reorder=getattr(preset, 'use_context_reorder', False)
    )

    # 사용자 입력으로 관련 문서 검색
    user_input = state["user_input"]
    context = retriever.get_formatted_context(user_input)

    new_state = update_state(state, rag_context=context, current_step="retrieve")

    # [LOG] 실행 결과 로깅 및 히스토리 업데이트
    status = "SUCCESS"
    rag_context = new_state.get("rag_context")
    doc_count = len(rag_context.split('---')) if rag_context else 0

    # 활성화된 기능 라벨 생성
    features = []
    if getattr(preset, 'use_multi_query', False):
        features.append("MultiQ")
    if getattr(preset, 'use_reranker', False):
        features.append("Rerank")
    if getattr(preset, 'use_context_reorder', False):
        features.append("Reorder")
    feature_label = f" ({', '.join(features)})" if features else ""
    summary = f"검색된 문서: {doc_count}건{feature_label}"

    return update_step_history(new_state, "retrieve", status, summary, start_time=start_time)


# ... (상단 생략)




def should_ask_user(state: PlanCraftState) -> AnalyzerRoutes:
    """
    Analyze 노드 이후 조건부 라우터.

    Return Type: AnalyzerRoutes = Literal["option_pause", "general_response", "structure"]

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                     판정표 (Decision Table)                             │
    ├────────────────────────┬───────────────────────┬────────────────────────┤
    │ 조건                   │ 반환값                │ 다음 노드              │
    ├────────────────────────┼───────────────────────┼────────────────────────┤
    │ need_more_info == True │ RouteKey.OPTION_PAUSE │ option_pause (HITL)    │
    │ is_general_query       │ RouteKey.GENERAL_RESP │ general_response       │
    │ (기본)                 │ RouteKey.CONTINUE     │ structure (기획서 생성)│
    └────────────────────────┴───────────────────────┴────────────────────────┘

    Returns:
        AnalyzerRoutes: 다음 노드를 결정하는 라우팅 키 (Literal 타입)
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




# =============================================================================
# Agent 래퍼 함수 (TypedDict 호환)
# =============================================================================







# =============================================================================
# 워크플로우 생성
# =============================================================================

def create_workflow() -> StateGraph:
    """
    PlanCraft 워크플로우 생성 (기본 버전)

    Runtime Config 사용법 (PlanCraftConfig 참조):
        graph.invoke(input, config={"configurable": {
            "generation_preset": "quality",
            "max_refine_loops": 5,
            "temperature": 0.5,
        }})
    """
    from graph.state import PlanCraftInput, PlanCraftOutput

    # LangGraph 1.x: input_schema/output_schema 사용
    # config는 invoke() 시 configurable 딕셔너리로 전달
    # 스키마 정의: graph.state.PlanCraftConfig 참조
    workflow = StateGraph(
        PlanCraftState,
        input_schema=PlanCraftInput,
        output_schema=PlanCraftOutput,
    )

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
    def should_discuss_or_complete(state: PlanCraftState) -> ReviewerRoutes:
        """
        Review 후 Discussion 필요 여부 결정 (성능 최적화)

        Return Type: ReviewerRoutes = Literal["discussion", "refine", "format", "analyze"]

        ┌─────────────────────────────────────────────────────────────────────────┐
        │                     판정표 (Decision Table)                             │
        ├──────────────┬──────────────┬──────────────────┬───────────────────────┤
        │ 조건         │ 점수 범위    │ 반환값           │ 다음 노드             │
        ├──────────────┼──────────────┼──────────────────┼───────────────────────┤
        │ 품질 통과    │ score >= 9   │ RouteKey.COMPLETE│ format (즉시 완료)    │
        │ 품질 실패    │ score < 5    │ RouteKey.RESTART │ analyze (재분석)      │
        │ 중간 품질    │ 7 <= s < 9   │ RouteKey.SKIP    │ refine (토론 스킵)    │
        │ 낮은 품질    │ 5 <= s < 7   │ RouteKey.DISCUSS │ discussion (토론 필요)│
        └──────────────┴──────────────┴──────────────────┴───────────────────────┘

        Note:
            DISCUSSION_SKIP_THRESHOLD (기본값: 7) 이상이면 Discussion 없이 Refine
        """
        logger = get_file_logger()
        review = state.get("review", {})
        score = review.get("overall_score", QualityThresholds.FALLBACK_SCORE)
        verdict = review.get("verdict", "REVISE")

        # PASS 판정: 바로 완료
        if QualityThresholds.is_pass(score) and verdict == "PASS":
            logger.info(f"[ROUTING] 품질 우수 ({score}점), 바로 완료")
            return RouteKey.COMPLETE

        # FAIL 판정: Analyzer 복귀
        if QualityThresholds.is_fail(score) or verdict == "FAIL":
            logger.info(f"[ROUTING] 품질 부족 ({score}점), Analyzer 복귀")
            return RouteKey.RESTART

        # 중간 점수: Discussion 스킵하고 바로 Refine
        if QualityThresholds.should_skip_discussion(score):
            logger.info(f"[ROUTING] 중간 품질 ({score}점), Discussion 스킵 → Refine")
            return RouteKey.SKIP_TO_REFINE

        # 낮은 점수: Discussion 필요
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
    def should_refine_again(state: PlanCraftState) -> RefinerRoutes:
        """
        Refiner 후 다음 단계 결정 (Graceful End-of-Loop 패턴 적용)

        Return Type: RefinerRoutes = Literal["structure", "format"]

        ┌─────────────────────────────────────────────────────────────────────────┐
        │                     판정표 (Decision Table)                             │
        ├────────────────────────┬─────────────────┬──────────────────────────────┤
        │ 조건                   │ 반환값          │ 설명                         │
        ├────────────────────────┼─────────────────┼──────────────────────────────┤
        │ remaining_steps <= 5   │ RouteKey.COMPLETE│ 스텝 부족 → 안전 종료       │
        │ refine_count >= MAX    │ RouteKey.COMPLETE│ 최대 루프 도달 → 종료       │
        │ refined == True        │ RouteKey.RETRY  │ 개선 필요 → structure 재실행│
        │ refined == False       │ RouteKey.COMPLETE│ 개선 완료 → format          │
        └────────────────────────┴─────────────────┴──────────────────────────────┘

        Note:
            Graceful End-of-Loop: 무한 루프 방지를 위한 다중 안전장치 적용
            [REFACTOR] 품질 프리셋 기반 max_refine_loops 동적 적용
        """
        from utils.settings import get_preset

        refined = state.get("refined", False)
        refine_count = state.get("refine_count", 0)
        remaining_steps = state.get("remaining_steps", 100)  # 기본값 충분히 크게

        # [REFACTOR] 품질 프리셋 기반 MAX_REFINE_LOOPS 동적 적용
        preset_key = state.get("generation_preset", "balanced")
        preset = get_preset(preset_key)
        max_refine_loops = preset.max_refine_loops

        # [NEW] Graceful End-of-Loop: 남은 스텝이 부족하면 안전하게 종료
        if remaining_steps <= settings.MIN_REMAINING_STEPS:
            print(f"[WARN] 남은 스텝 부족 ({remaining_steps}), 루프 종료")
            return RouteKey.COMPLETE

        # 최대 루프 횟수 초과 (프리셋 기반)
        if refine_count >= max_refine_loops:
            print(f"[WARN] 최대 루프 도달 ({refine_count}/{max_refine_loops}, Preset: {preset_key}), 루프 종료")
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
    
    from graph.state import PlanCraftInput, PlanCraftOutput

    workflow = StateGraph(
        PlanCraftState,
        input_schema=PlanCraftInput,
        output_schema=PlanCraftOutput,
    )

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


def compile_workflow(use_subgraphs: bool = False, checkpointer = None):
    """
    워크플로우 컴파일
    
    Args:
        use_subgraphs: 서브그래프 패턴 사용 여부
        checkpointer: [Optional] 외부 주입 Checkpointer (테스트용)
    """
    # 체크포인터 설정 (외부 주입 없으면 기본값 사용)
    if checkpointer is None:
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
    resume_command: dict = None,  # [NEW] 재개를 위한 커맨드 데이터
    generation_preset: str = None  # [NEW] 생성 모드 프리셋 (fast/balanced/quality)
) -> dict:
    """
    PlanCraft 워크플로우 실행 엔트리포인트

    Args:
        user_input: 사용자 입력 텍스트
        file_content: 업로드된 파일 내용 (선택)
        refine_count: 현재 개선 횟수
        previous_plan: 이전 기획서 (개선 모드)
        callbacks: LangChain 콜백 리스트
        thread_id: 세션 ID
        resume_command: 인터럽트 후 재개를 위한 데이터 (Command resume)
        generation_preset: 생성 모드 프리셋 ("fast", "balanced", "quality")
    """
    from graph.state import create_initial_state
    from langgraph.types import Command
    from utils.settings import DEFAULT_PRESET

    # [UPDATE] Input Schema 분리에 따른 입력 구성
    inputs = None
    if not resume_command:
        # 처음 시작할 때만 입력 구성
        inputs = {
            "user_input": user_input,
            "file_content": file_content,
            "refine_count": refine_count,
            "previous_plan": previous_plan,
            "thread_id": thread_id,
            "generation_preset": generation_preset or DEFAULT_PRESET,  # [NEW]
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

    # 실행 (stream 모드로 타임라인 업데이트 지원)
    # 각 노드 완료 시 콜백의 set_step 호출
    final_state = None

    # 노드 이름 → 타임라인 단계 매핑 (워크플로우 add_node 이름과 일치!)
    NODE_TO_STEP = {
        "context_gathering": "context",   # SubGraph
        "analyze": "analyze",
        "option_pause": "analyze",
        "general_response": "analyze",
        "structure": "structure",
        "write": "write",
        "review": "review",
        "discussion": "discuss",
        "refine": "refine",
        "format": "format",
    }

    # StreamlitStatusCallback 찾기
    timeline_callback = None
    if callbacks:
        for cb in callbacks:
            if hasattr(cb, "set_step"):
                timeline_callback = cb
                break

    # stream 모드로 실행하여 노드별 진행상황 추적
    for event in app.stream(input_data, config=config, stream_mode="updates"):
        final_state = event

        # 노드 이름 추출 및 타임라인 업데이트
        if isinstance(event, dict):
            for node_name in event.keys():
                step_key = NODE_TO_STEP.get(node_name)
                if step_key and timeline_callback:
                    timeline_callback.set_step(step_key)

    # 타임라인 완료 처리
    if timeline_callback:
        timeline_callback.finish()

    # [NEW] 인터럽트 상태 및 최종 상태 확인
    snapshot = app.get_state(config)

    # stream 모드에서는 snapshot.values에서 전체 상태 가져오기
    final_state = snapshot.values if snapshot.values else final_state

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
        result = dict(final_state)

    # 인터럽트 정보 추가
    if interrupt_payload:
        result["__interrupt__"] = interrupt_payload

    # [NEW] 토큰 사용량 추적 (콜백에서 수집)
    if callbacks:
        for cb in callbacks:
            if hasattr(cb, "get_usage_summary"):
                usage = cb.get_usage_summary()
                if usage.get("total_tokens", 0) > 0:
                    result["token_usage"] = usage
                    # Checkpointer에도 저장 (polling 시 조회 가능하도록)
                    try:
                        app.update_state(config, {"token_usage": usage})
                    except Exception:
                        pass  # 저장 실패해도 result에는 포함됨
                break

    return result
