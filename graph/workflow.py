"""
PlanCraft Agent - LangGraph 워크플로우 정의

Multi-Agent 파이프라인을 LangGraph StateGraph로 정의합니다.
각 Agent는 노드로 등록되며, 조건부 엣지를 통해 흐름을 제어합니다.

워크플로우 구조:
    +-------------+
    |   START     |
    +------+------+
           |
    +------v------+
    |  retrieve   |  <- RAG 검색
    +------+------+
           |
    +------v------+
    | fetch_web   |  <- 웹 정보 조회 (MCP)
    +------+------+
           |
    +------v------+     need_more_info=True    +---------+
    |   analyze   | --------------------------> |   END   |
    +------+------+                             +---------+
           | need_more_info=False
    +------v------+
    |  structure  |
    +------+------+
           |
    +------v------+
    |    write    |
    +------+------+
           |
    +------v------+
    |   review    |  <- 검토 및 피드백
    +------+------+
           |
    +------v------+
    |   refine    |  <- 피드백 반영하여 개선
    +------+------+
           |
    +------v------+
    |   format    |  <- 사용자 친화적 요약 생성
    +------+------+
           |
    +------v------+
    |     END     |
    +-------------+

Best Practice 적용:
    - InputState/OutputState 분리: API 경계 명확화
    - PlanCraftState 타입 어노테이션: 모든 노드 함수에 적용

사용 예시:
    from graph.workflow import run_plancraft

    result = run_plancraft("점심 메뉴 추천 앱을 만들고 싶어요")
    print(result["final_output"])
"""

from langgraph.graph import StateGraph, END
from graph.state import PlanCraftState, InputState, OutputState
from agents import analyzer, structurer, writer, reviewer, refiner, formatter


# =============================================================================
# 노드 함수 정의 (모두 PlanCraftState 타입 명시)
# =============================================================================

def retrieve_context(state: PlanCraftState) -> PlanCraftState:
    """
    RAG를 통해 관련 컨텍스트를 검색하는 노드

    사용자 입력을 기반으로 가이드 문서에서 관련 내용을 검색합니다.
    검색 실패 시에도 워크플로우는 계속 진행됩니다.

    Args:
        state: 현재 워크플로우 상태 (PlanCraftState)

    Returns:
        PlanCraftState: rag_context가 추가된 상태
    """
    try:
        from rag.retriever import Retriever

        # Retriever 초기화 (상위 3개 문서 검색)
        retriever = Retriever(k=3)

        # 사용자 입력으로 관련 문서 검색
        user_input = state.get("user_input", "")
        context = retriever.get_formatted_context(user_input)

        state["rag_context"] = context
        state["current_step"] = "retrieve"

    except Exception as e:
        # RAG 실패 시에도 계속 진행 (graceful degradation)
        state["rag_context"] = ""
        state["error"] = f"RAG 검색 실패: {str(e)}"

    return state


def fetch_web_context(state: PlanCraftState) -> PlanCraftState:
    """
    조건부 웹 정보 수집 노드 (Supervisor 역할)

    다음 조건에서만 웹 검색/조회를 수행합니다:
    1. URL이 직접 제공된 경우 -> 해당 URL fetch
    2. 최신 정보가 필요한 경우 -> DuckDuckGo 검색
    3. 외부 시장/기술 정보가 필요한 경우 -> DuckDuckGo 검색

    내부 문서 질의나 RAG로 충분한 경우에는 검색하지 않습니다.
    이는 불필요한 외부 호출을 방지하고, Agent의 판단 능력을 보여줍니다.

    Args:
        state: 현재 워크플로우 상태 (PlanCraftState)

    Returns:
        PlanCraftState: web_context가 추가된 상태
    """
    import re

    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")
    web_contents = []
    web_urls = []

    try:
        # =====================================================================
        # 1. URL이 직접 제공된 경우 -> URL Fetch
        # =====================================================================
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, user_input)

        if urls:
            from mcp.web_client import fetch_url_sync

            for url in urls[:3]:  # 최대 3개 URL
                try:
                    content = fetch_url_sync(url, max_length=3000)
                    if content and not content.startswith("[웹 조회 실패"):
                        web_contents.append(f"[URL 참조: {url}]\n{content}")
                        web_urls.append(url)
                except Exception as e:
                    print(f"[WARN] URL 조회 실패 ({url}): {e}")

            print(f"[INFO] URL 직접 참조: {len(web_urls)}개")

        # =====================================================================
        # 2. URL이 없으면 조건부 웹 검색 판단
        # =====================================================================
        else:
            from mcp.web_search import conditional_web_search

            search_result = conditional_web_search(user_input, rag_context)

            if search_result["searched"]:
                web_contents.append(search_result["context"])
                print(f"[INFO] 웹 검색 수행: {search_result['reason']}")
            else:
                print(f"[INFO] 웹 검색 스킵: {search_result['reason']}")

        # =====================================================================
        # 3. 상태 업데이트
        # =====================================================================
        if web_contents:
            state["web_context"] = "\n\n---\n\n".join(web_contents)
            state["web_urls"] = web_urls
        else:
            state["web_context"] = None
            state["web_urls"] = []

        state["current_step"] = "fetch_web"

    except Exception as e:
        # 웹 조회 실패 시에도 계속 진행 (graceful degradation)
        state["web_context"] = None
        state["web_urls"] = []
        print(f"[WARN] 웹 조회 단계 오류: {e}")

    return state


def should_ask_user(state: PlanCraftState) -> str:
    """
    분석 후 추가 정보가 필요한지 판단하는 조건부 라우터

    Analyzer Agent의 need_more_info 필드를 확인하여
    워크플로우를 중단할지 계속할지 결정합니다.

    Args:
        state: 현재 워크플로우 상태 (PlanCraftState)

    Returns:
        str: "ask_user" (중단) 또는 "continue" (계속)
    """
    if state.get("need_more_info", False):
        return "ask_user"  # 추가 정보 필요 -> 워크플로우 중단
    return "continue"       # 정보 충분 -> 다음 단계로


# =============================================================================
# 워크플로우 생성 (Input/Output Schema 적용)
# =============================================================================

def create_workflow() -> StateGraph:
    """
    PlanCraft 워크플로우를 생성합니다.

    LangGraph Best Practice:
    - PlanCraftState: 내부 워크플로우 전체 상태
    - InputState: 외부에서 들어오는 입력 스키마 (선택적 적용)
    - OutputState: 외부로 나가는 출력 스키마 (선택적 적용)

    Note: LangGraph 0.1.x에서 input/output 스키마는 invoke 시 자동 필터링됩니다.
          여기서는 내부 상태로 PlanCraftState를 사용합니다.

    Returns:
        StateGraph: 구성된 워크플로우 (컴파일 전)
    """
    # StateGraph 생성 (내부 상태 타입 지정)
    # NOTE: input/output 스키마는 필요 시 compile() 단계에서 설정 가능
    workflow = StateGraph(PlanCraftState)

    # =========================================================================
    # 노드 등록 (모든 Agent는 PlanCraftState 타입 사용)
    # =========================================================================
    workflow.add_node("retrieve", retrieve_context)   # RAG 검색
    workflow.add_node("fetch_web", fetch_web_context) # 웹 정보 조회
    workflow.add_node("analyze", analyzer.run)        # 입력 분석
    workflow.add_node("structure", structurer.run)    # 구조 설계
    workflow.add_node("write", writer.run)            # 내용 작성
    workflow.add_node("review", reviewer.run)         # 검토
    workflow.add_node("refine", refiner.run)          # 피드백 반영 개선
    workflow.add_node("format", formatter.run)        # 사용자 친화적 포맷팅

    # =========================================================================
    # 엣지 정의
    # =========================================================================

    # 시작점 설정 (RAG 검색부터 시작)
    workflow.set_entry_point("retrieve")

    # retrieve -> fetch_web -> analyze (순차)
    workflow.add_edge("retrieve", "fetch_web")
    workflow.add_edge("fetch_web", "analyze")

    # analyze -> (조건부 분기)
    # - need_more_info=True: END (사용자에게 질문 반환)
    # - need_more_info=False: structure (계속 진행)
    workflow.add_conditional_edges(
        "analyze",
        should_ask_user,
        {
            "ask_user": END,
            "continue": "structure"
        }
    )

    # structure -> write -> review -> refine -> format -> END (순차)
    workflow.add_edge("structure", "write")
    workflow.add_edge("write", "review")
    workflow.add_edge("review", "refine")
    workflow.add_edge("refine", "format")
    workflow.add_edge("format", END)

    return workflow


def compile_workflow():
    """
    워크플로우를 컴파일하여 실행 가능한 앱으로 반환합니다.

    Returns:
        CompiledGraph: 실행 가능한 컴파일된 워크플로우
    """
    workflow = create_workflow()
    return workflow.compile()


# =============================================================================
# 전역 앱 인스턴스
# =============================================================================
# 모듈 로드 시 한 번만 컴파일 (성능 최적화)
app = compile_workflow()


# =============================================================================
# 실행 함수
# =============================================================================

def run_plancraft(user_input: str, file_content: str = None) -> PlanCraftState:
    """
    PlanCraft Agent 워크플로우를 실행합니다.

    사용자 입력을 받아 전체 파이프라인을 실행하고
    최종 상태(기획서 포함)를 반환합니다.

    Args:
        user_input: 사용자의 아이디어/요청 텍스트
        file_content: 참고 파일 내용 (선택)

    Returns:
        PlanCraftState: 최종 상태 딕셔너리
            - final_output: 생성된 기획서 (마크다운)
            - chat_summary: 채팅용 요약
            - need_more_info: 추가 정보 필요 여부
            - options: 선택 옵션 (need_more_info=True일 때)

    Example:
        >>> result = run_plancraft("점심 메뉴 추천 앱을 만들고 싶어요")
        >>> if result["need_more_info"]:
        ...     print("추가 질문:", result["option_question"])
        ... else:
        ...     print(result["final_output"])

    Raises:
        Exception: LLM 호출 실패 등 오류 발생 시
    """
    from graph.state import create_initial_state

    # 초기 상태 생성
    initial_state = create_initial_state(user_input, file_content)

    # 워크플로우 실행
    final_state = app.invoke(initial_state)

    return final_state
