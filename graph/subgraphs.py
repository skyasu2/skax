"""
PlanCraft Agent - Sub-graph 정의 모듈

LangGraph 베스트 프랙티스에 따라 관련 노드들을 Sub-graph로 그룹화합니다.
각 Sub-graph는 명확한 책임을 가지며, 독립적으로 테스트/재사용 가능합니다.

Sub-graph 구조:
    1. Context Sub-graph: 정보 수집 (RAG + 웹 검색)
    2. Generation Sub-graph: 콘텐츠 생성 (분석 → 구조 → 작성)
    3. QA Sub-graph: 품질 관리 (검토 → 개선 → 포맷)
    4. Discussion Sub-graph: 에이전트 간 대화 (Reviewer ↔ Writer)

Best Practice:
    - 각 Sub-graph는 독립적으로 컴파일 가능
    - 메인 Graph에서 Sub-graph를 노드로 추가
    - 명확한 책임 분리로 유지보수성 향상

⚠️ INTERRUPT 동작 주의사항 (후임자/팀원 필독):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SubGraph 내부에서 interrupt()가 호출되면, Resume 시:
1. SubGraph를 호출한 부모 노드(run_*_subgraph 함수) 전체가 재실행됨
2. SubGraph 자체도 처음부터 다시 시작됨
3. interrupt() 이전의 모든 코드가 다시 실행됨

따라서:
- interrupt() 전에는 Side-Effect(DB 저장, API 호출, 알림 발송) 금지
- 초기화 코드(discussion_messages=[] 등)는 Resume 시 다시 실행됨을 인지
- 외부 시스템 연동 시: State에 스냅샷 저장 또는 별도 저장소 백업 필요
- 자세한 내용: docs/HITL_GUIDE.md 참조
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
# Discussion Sub-graph: 에이전트 간 대화 (Reviewer ↔ Writer)
# =============================================================================

def create_discussion_subgraph() -> StateGraph:
    """
    Discussion Sub-graph 생성

    책임: Reviewer와 Writer가 대화하며 개선 방향 합의
    입력: draft, review
    출력: discussion_messages, agreed_action_items

    대화 흐름:
        reviewer_speak → writer_respond → check_consensus
                              ↑                │
                              └────── NO ──────┘
                                       │
                                      YES
                                       ↓
                                      END
    """
    from graph.state import update_state

    subgraph = StateGraph(PlanCraftState)

    # 노드 등록
    subgraph.add_node("reviewer_speak", _reviewer_speak_node)
    subgraph.add_node("writer_respond", _writer_respond_node)
    subgraph.add_node("check_consensus", _check_consensus_node)

    # 흐름 정의
    subgraph.set_entry_point("reviewer_speak")
    subgraph.add_edge("reviewer_speak", "writer_respond")
    subgraph.add_edge("writer_respond", "check_consensus")

    # 조건부 엣지: 합의 여부에 따라 종료 또는 반복
    subgraph.add_conditional_edges(
        "check_consensus",
        _should_continue_discussion,
        {
            "continue": "reviewer_speak",  # 대화 계속
            "end": END  # 합의 도달
        }
    )

    return subgraph


def _reviewer_speak_node(state: PlanCraftState) -> PlanCraftState:
    """Reviewer가 피드백을 제시하는 노드"""
    from graph.state import update_state
    from utils.llm import get_llm
    from prompts.discussion_prompt import REVIEWER_DISCUSSION_PROMPT

    # 대화 이력 가져오기
    discussion_messages = state.get("discussion_messages", [])
    review = state.get("review", {})
    draft = state.get("draft", {})
    discussion_round = state.get("discussion_round", 0)

    # 첫 번째 라운드: 초기 피드백 제시
    if discussion_round == 0:
        feedback = review.get("feedback_summary", "")
        critical_issues = review.get("critical_issues", [])
        action_items = review.get("action_items", [])

        initial_message = f"""[초기 피드백]
지적 사항: {feedback}
치명적 문제: {', '.join(critical_issues) if critical_issues else '없음'}
필요한 조치: {', '.join(action_items) if action_items else '없음'}

Writer님, 위 피드백에 대해 어떻게 개선할 계획인지 말씀해주세요."""

        discussion_messages.append({
            "role": "reviewer",
            "content": initial_message,
            "round": discussion_round
        })
    else:
        # 후속 라운드: Writer 응답에 대한 Reviewer 반응
        llm = get_llm(temperature=0.3)

        # 이전 대화 컨텍스트 구성
        context = "\n".join([
            f"[{m['role'].upper()}]: {m['content']}"
            for m in discussion_messages[-4:]  # 최근 4개 메시지만
        ])

        messages = [
            {"role": "system", "content": REVIEWER_DISCUSSION_PROMPT},
            {"role": "user", "content": f"""이전 대화:
{context}

Writer의 개선 계획을 검토하고, 추가 조언이나 확인이 필요하면 말씀하세요.
충분하다고 판단되면 "합의 완료"라고 말씀하세요."""}
        ]

        response = llm.invoke(messages)

        discussion_messages.append({
            "role": "reviewer",
            "content": response.content,
            "round": discussion_round
        })

    return update_state(
        state,
        discussion_messages=discussion_messages,
        discussion_round=discussion_round,
        current_step="discussion_reviewer"
    )


def _writer_respond_node(state: PlanCraftState) -> PlanCraftState:
    """Writer가 Reviewer 피드백에 응답하는 노드"""
    from graph.state import update_state
    from utils.llm import get_llm
    from prompts.discussion_prompt import WRITER_DISCUSSION_PROMPT

    discussion_messages = state.get("discussion_messages", [])
    draft = state.get("draft", {})
    discussion_round = state.get("discussion_round", 0)

    llm = get_llm(temperature=0.4)

    # 이전 대화 컨텍스트 구성
    context = "\n".join([
        f"[{m['role'].upper()}]: {m['content']}"
        for m in discussion_messages[-4:]
    ])

    # Draft 요약
    sections = draft.get("sections", []) if isinstance(draft, dict) else []
    draft_summary = ", ".join([
        s.get("name", "") if isinstance(s, dict) else s.name
        for s in sections[:5]
    ])

    messages = [
        {"role": "system", "content": WRITER_DISCUSSION_PROMPT},
        {"role": "user", "content": f"""현재 기획서 섹션: {draft_summary}

이전 대화:
{context}

Reviewer의 피드백에 대해 구체적인 개선 계획을 제시하세요.
어떤 부분을 어떻게 수정할 것인지 명확하게 설명하세요."""}
    ]

    response = llm.invoke(messages)

    discussion_messages.append({
        "role": "writer",
        "content": response.content,
        "round": discussion_round
    })

    return update_state(
        state,
        discussion_messages=discussion_messages,
        current_step="discussion_writer"
    )


def _check_consensus_node(state: PlanCraftState) -> PlanCraftState:
    """대화 합의 여부를 체크하고 라운드를 증가시키는 노드"""
    from graph.state import update_state
    from utils.settings import settings

    discussion_round = state.get("discussion_round", 0) + 1
    discussion_messages = state.get("discussion_messages", [])

    # 합의 여부 판단
    consensus_reached = False

    if discussion_messages:
        last_reviewer_msg = None
        for msg in reversed(discussion_messages):
            if msg.get("role") == "reviewer":
                last_reviewer_msg = msg.get("content", "")
                break

        if last_reviewer_msg:
            # "합의", "동의", "좋습니다", "진행하세요" 등의 키워드 체크
            consensus_keywords = ["합의", "동의", "좋습니다", "진행", "승인", "완료"]
            consensus_reached = any(kw in last_reviewer_msg for kw in consensus_keywords)

    # 최대 라운드 도달 시 강제 합의
    max_rounds = getattr(settings, 'DISCUSSION_MAX_ROUNDS', 3)
    if discussion_round >= max_rounds:
        consensus_reached = True
        discussion_messages.append({
            "role": "system",
            "content": f"[최대 대화 라운드({max_rounds}회) 도달. 현재 논의 내용을 바탕으로 진행합니다.]",
            "round": discussion_round
        })

    # 합의된 액션 아이템 추출
    agreed_items = []
    if consensus_reached:
        for msg in discussion_messages:
            if msg.get("role") == "writer":
                content = msg.get("content", "")
                # 간단한 액션 아이템 추출 (실제로는 LLM으로 추출 가능)
                if "수정" in content or "추가" in content or "보완" in content:
                    agreed_items.append(content[:100])  # 요약

    return update_state(
        state,
        discussion_round=discussion_round,
        discussion_messages=discussion_messages,
        consensus_reached=consensus_reached,
        agreed_action_items=agreed_items,
        current_step="discussion_check"
    )


def _should_continue_discussion(state: PlanCraftState) -> str:
    """대화를 계속할지 결정하는 조건 함수"""
    if state.get("consensus_reached", False):
        return "end"
    return "continue"


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
    컨텍스트 수집 서브그래프 (Context Sub-graph)
    
    [PHASE 2] RAG 검색과 웹 검색을 병렬로 수행하여 성능 향상
    
    변경 전: RAG → Web (순차, ~5초)
    변경 후: RAG + Web (병렬, ~3초)
    """
    from graph.workflow import retrieve_context, fetch_web_context
    from graph.state import update_state
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time
    
    # 1. 초기 상태 로깅
    current_history = state.get("step_history", []) or []
    print(f"[Subgraph] 병렬 Context Gathering Started")
    start_time = time.time()
    
    # =========================================================================
    # [PHASE 2] 병렬 실행: RAG + 웹검색 동시 수행
    # =========================================================================
    rag_result = None
    web_result = None
    
    def run_rag():
        return retrieve_context(state)
    
    def run_web():
        return fetch_web_context(state)
    
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            rag_future = executor.submit(run_rag)
            web_future = executor.submit(run_web)
            
            # 결과 수집
            rag_result = rag_future.result(timeout=30)
            web_result = web_future.result(timeout=30)
            
    except Exception as e:
        print(f"[Subgraph] 병렬 실행 실패, 순차 실행으로 전환: {e}")
        # Fallback: 순차 실행
        rag_result = retrieve_context(state)
        web_result = fetch_web_context(rag_result)
    
    elapsed = time.time() - start_time
    print(f"[Subgraph] Context Gathering 완료 ({elapsed:.2f}초)")
    
    # 3. 결과 병합
    updates = {
        "rag_context": rag_result.get("rag_context") if rag_result else None,
        "web_context": web_result.get("web_context") if web_result else None,
        "web_urls": web_result.get("web_urls") if web_result else None,
        "web_sources": web_result.get("web_sources") if web_result else None,  # [FIX] 출처 정보 전달
        "current_step": "context_gathering",
        # History 병합 (둘 다 합침)
        "step_history": (rag_result.get("step_history") or []) +
                       [h for h in (web_result.get("step_history") or [])
                        if h not in (rag_result.get("step_history") or [])]
    }
    
    return update_state(state, **updates)


def run_generation_subgraph(state: PlanCraftState) -> PlanCraftState:
    """생성 서브그래프 (분석 -> 구조화 -> 작성)"""
    from graph.workflow import run_analyzer_node, run_structurer_node, run_writer_node
    from graph.state import update_state
    
    s1 = run_analyzer_node(state)
    
    # 분기 로직 처리 (Interrupt 등)은 Main Graph에서 담당하므로
    # 여기서는 순차적으로 Happy Path만 시뮬레이션하거나, 
    # 실제로는 Graph를 리턴해야 함. (구조 변경 필요)
    
    # 현재 구조상 함수 직접 호출로 진행
    if s1.get("need_more_info"):
        return s1 # 인터럽트 필요 시 바로 반환
        
    s2 = run_structurer_node(s1)
    s3 = run_writer_node(s2)
    
    return s3


def run_qa_subgraph(state: PlanCraftState) -> PlanCraftState:
    """QA 서브그래프 (검토 -> 개선 -> 포맷)"""
    from graph.workflow import run_reviewer_node, run_refiner_node, run_formatter_node

    s1 = run_reviewer_node(state)
    s2 = run_refiner_node(s1)
    s3 = run_formatter_node(s2)

    return s3


def get_discussion_app():
    """Discussion Sub-graph 컴파일된 앱 반환"""
    return create_discussion_subgraph().compile()


def run_discussion_subgraph(state: PlanCraftState) -> PlanCraftState:
    """
    에이전트 간 대화 서브그래프 (Reviewer ↔ Writer)

    Reviewer가 피드백을 제시하고, Writer가 개선 계획을 설명하며,
    합의에 도달할 때까지 대화를 진행합니다.

    입력: draft, review
    출력: discussion_messages, agreed_action_items, consensus_reached

    ⚠️ INTERRUPT 주의사항:
    현재 이 SubGraph에는 interrupt()가 없으므로 안전합니다.
    만약 향후 interrupt를 추가한다면, Resume 시 이 함수 전체가
    재실행되므로 아래 초기화 코드가 다시 실행됩니다.
    (discussion_messages=[], discussion_round=0 등)
    → docs/HITL_GUIDE.md 참조
    """
    from graph.state import update_state
    import time

    print("[Discussion SubGraph] 에이전트 간 대화 시작")
    start_time = time.time()

    # 대화 상태 초기화 (기존 대화 이력이 없거나, 새 세션인 경우만)
    # Resume 시에는 기존 상태를 유지해야 함 (Idempotency 보장)
    if not state.get("discussion_messages"):
        state = update_state(
            state,
            discussion_messages=[],
            discussion_round=0,
            consensus_reached=False,
            agreed_action_items=[]
        )

    # 서브그래프 실행
    discussion_app = get_discussion_app()
    result = discussion_app.invoke(state)

    elapsed = time.time() - start_time
    round_count = result.get("discussion_round", 0)
    msg_count = len(result.get("discussion_messages", []))

    print(f"[Discussion SubGraph] 대화 완료 ({elapsed:.2f}초, {round_count}라운드, {msg_count}메시지)")

    # step_history에 대화 요약 추가
    current_history = result.get("step_history", []) or []
    discussion_summary = {
        "step": "discussion",
        "status": "SUCCESS",
        "summary": f"Reviewer-Writer 대화 {round_count}라운드 완료, 합의: {result.get('consensus_reached', False)}",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "execution_time": f"{elapsed:.2f}s"
    }

    return update_state(
        result,
        step_history=current_history + [discussion_summary],
        current_step="discussion"
    )


# =============================================================================
# Multi-HITL 확장 패턴 (Future-proof Design)
# =============================================================================
#
# 다중 Human-in-the-Loop 시나리오를 위한 확장 가이드
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │                    Multi-HITL Subgraph 아키텍처                          │
# ├─────────────────────────────────────────────────────────────────────────┤
# │                                                                         │
# │  [Context Subgraph]                                                     │
# │       │                                                                 │
# │       ▼                                                                 │
# │  ┌─────────┐    ┌─────────────┐    ┌─────────┐                         │
# │  │ Analyze │───▶│ HITL: 방향  │───▶│Structure│                         │
# │  └─────────┘    │   선택      │    └─────────┘                         │
# │                 └─────────────┘         │                              │
# │                                         ▼                              │
# │                 ┌─────────────┐    ┌─────────┐                         │
# │                 │ HITL: 구조  │◀───│  Write  │                         │
# │                 │   승인      │    └─────────┘                         │
# │                 └─────────────┘                                        │
# │                       │                                                │
# │                       ▼                                                │
# │  [QA Subgraph with Optional Human Approval]                            │
# │                                                                         │
# └─────────────────────────────────────────────────────────────────────────┘
#
# 사용 예시: 각 단계별 Human Approval이 필요한 경우
#
# def create_approval_pause_node(stage_name: str):
#     """
#     재사용 가능한 Approval Pause Node Factory
#
#     ⚠️ CRITICAL: interrupt() 전에는 Side-Effect 금지!
#     """
#     def approval_pause(state: PlanCraftState) -> Command:
#         from langgraph.types import interrupt, Command
#
#         # 1. 승인 요청 페이로드 생성 (순수 함수)
#         payload = {
#             "type": "approval",
#             "stage": stage_name,
#             "question": f"{stage_name} 단계 결과를 승인하시겠습니까?",
#             "data": state.get(stage_name.lower(), {}),
#         }
#
#         # 2. interrupt() 호출 (이 시점에서 실행 중단)
#         user_response = interrupt(payload)
#
#         # 3. Resume 후 실행되는 코드 (Side-Effect 허용)
#         if user_response.get("approved"):
#             return Command(goto="next_stage")
#         else:
#             return Command(goto="revision_stage")
#
#     return approval_pause
#
# 위 패턴으로 각 Subgraph에 Approval Node를 추가할 수 있습니다.
# 자세한 구현은 graph/workflow.py의 option_pause_node()를 참조하세요.
#
