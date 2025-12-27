"""
PlanCraft Agent - 상태 정의 모듈

LangGraph 워크플로우에서 사용하는 상태(State) 타입을 정의합니다.
모든 Agent는 이 State를 입력받아 처리 후 업데이트된 State를 반환합니다.

워크플로우 흐름:
    [사용자 입력] -> retrieve -> fetch_web -> analyze -> structure -> write -> review -> refine -> format -> [최종 출력]

    Judge(Reviewer) 판정:
    - PASS: 수정 없이 통과
    - REVISE: action_items 반영하여 개선
    - FAIL: 전면 재설계

Best Practice 적용:
    - InputState: 외부에서 그래프로 들어오는 입력만 정의
    - OutputState: 그래프에서 외부로 나가는 출력만 정의
    - PlanCraftState: 내부 워크플로우 전체 상태

사용 예시:
    from graph.state import PlanCraftState, InputState, OutputState, create_initial_state

    # 초기 상태 생성
    state = create_initial_state("점심 메뉴 추천 앱을 만들고 싶어요")

    # Agent가 상태 업데이트
    state["analysis"] = {...}
"""

from typing import TypedDict, Optional, List


# =============================================================================
# Input Schema - 외부에서 그래프로 들어오는 입력
# =============================================================================
class InputState(TypedDict):
    """
    그래프 입력 스키마 (LangGraph Best Practice)

    외부 API나 사용자로부터 받는 입력만 정의합니다.
    내부 워크플로우 상태와 분리하여 API 경계를 명확히 합니다.

    Attributes:
        user_input: 사용자가 입력한 원본 텍스트
        file_content: 참고 파일 내용 (선택)
    """
    user_input: str
    file_content: Optional[str]


# =============================================================================
# Output Schema - 그래프에서 외부로 나가는 출력
# =============================================================================
class OutputState(TypedDict):
    """
    그래프 출력 스키마 (LangGraph Best Practice)

    외부로 반환할 결과만 정의합니다.
    내부 상태(점수, 판정 등)는 노출하지 않습니다.

    Attributes:
        final_output: 완성된 기획서 (마크다운)
        chat_summary: 채팅용 요약 메시지
        need_more_info: 추가 정보 필요 여부
        options: 사용자 선택 옵션 (need_more_info=True일 때)
        option_question: 옵션 선택 질문
    """
    final_output: Optional[str]
    chat_summary: Optional[str]
    need_more_info: bool
    options: Optional[List[dict]]
    option_question: Optional[str]


# =============================================================================
# Internal State - 워크플로우 전체 상태
# =============================================================================
class PlanCraftState(TypedDict):
    """
    PlanCraft Agent의 워크플로우 상태 정의

    LangGraph의 StateGraph에서 사용하는 내부 상태 타입입니다.
    각 Agent는 이 State를 받아서 자신의 출력을 추가합니다.

    Note:
        - InputState: 외부 입력만 (user_input, file_content)
        - OutputState: 외부 출력만 (final_output, chat_summary, ...)
        - PlanCraftState: 전체 내부 상태 (InputState + 중간 상태 + OutputState)

    Attributes:
        user_input: 사용자가 입력한 원본 텍스트
        file_content: MCP를 통해 불러온 참고 파일 내용
        rag_context: RAG 검색으로 가져온 관련 가이드 문서
        analysis: Analyzer Agent의 분석 결과 (dict)
        need_more_info: 추가 정보 필요 여부 (True면 워크플로우 중단)
        questions: 사용자에게 할 추가 질문 목록
        structure: Structurer Agent의 구조 설계 결과 (dict)
        draft: Writer Agent의 초안 (dict)
        review: Reviewer Agent의 검토 결과 (dict) - 내부용, 외부 노출 안함
        final_output: 최종 출력물 (마크다운 문자열)
        current_step: 현재 처리 중인 단계 이름
        error: 오류 발생 시 오류 메시지
    """

    # =========================================================================
    # 입력 데이터 (InputState와 동일)
    # =========================================================================
    user_input: str                      # 사용자 원본 입력
    file_content: Optional[str]          # MCP로 불러온 파일 내용

    # =========================================================================
    # RAG 컨텍스트
    # =========================================================================
    rag_context: Optional[str]           # 검색된 참고 문서

    # =========================================================================
    # 웹 조회 컨텍스트
    # =========================================================================
    web_context: Optional[str]           # 웹에서 가져온 참고 정보
    web_urls: Optional[List[str]]        # 조회한 URL 목록

    # =========================================================================
    # Analyzer Agent 출력
    # =========================================================================
    analysis: Optional[dict]             # 분석 결과
    need_more_info: bool                 # 추가 정보 필요 여부
    options: Optional[List[dict]]        # A/B/C 선택 옵션
    option_question: Optional[str]       # 옵션 선택을 위한 질문
    selected_option: Optional[str]       # 사용자가 선택한 옵션

    # =========================================================================
    # 대화 히스토리 (Memory)
    # =========================================================================
    messages: Optional[List[dict]]       # 대화 히스토리 [{"role": "user/assistant", "content": "..."}]

    # =========================================================================
    # Structurer Agent 출력
    # =========================================================================
    structure: Optional[dict]            # 기획서 구조

    # =========================================================================
    # Writer Agent 출력
    # =========================================================================
    draft: Optional[dict]                # 초안

    # =========================================================================
    # Reviewer(Judge) Agent 출력 - 내부용, 외부 노출 안함
    # =========================================================================
    review: Optional[dict]               # 심사 결과 (verdict, action_items 포함)

    # =========================================================================
    # Refiner Agent 출력
    # =========================================================================
    refined: Optional[bool]              # 개선 작업 수행 여부

    # =========================================================================
    # 최종 결과 (OutputState와 동일)
    # =========================================================================
    final_output: Optional[str]          # 최종 마크다운 출력 (전체 기획서)
    chat_summary: Optional[str]          # 채팅용 요약 메시지

    # =========================================================================
    # 메타데이터
    # =========================================================================
    current_step: Optional[str]          # 현재 단계
    error: Optional[str]                 # 오류 메시지


def create_initial_state(user_input: str, file_content: str = None) -> PlanCraftState:
    """
    초기 상태를 생성합니다.

    워크플로우 시작 시 호출하여 빈 상태를 초기화합니다.

    Args:
        user_input: 사용자가 입력한 아이디어/요청 텍스트
        file_content: 참고할 파일 내용 (선택)

    Returns:
        PlanCraftState: 초기화된 상태 딕셔너리

    Example:
        >>> state = create_initial_state("점심 메뉴 추천 앱을 만들고 싶어요")
        >>> print(state["user_input"])
        점심 메뉴 추천 앱을 만들고 싶어요
    """
    return PlanCraftState(
        # 입력
        user_input=user_input,
        file_content=file_content,

        # RAG
        rag_context=None,

        # 웹 컨텍스트
        web_context=None,
        web_urls=None,

        # Agent 출력 (모두 None으로 초기화)
        analysis=None,
        need_more_info=False,
        options=None,
        option_question=None,
        selected_option=None,

        # 대화 히스토리
        messages=[{"role": "user", "content": user_input}],

        # 이후 Agent 출력
        structure=None,
        draft=None,
        review=None,
        refined=None,
        final_output=None,
        chat_summary=None,

        # 메타데이터
        current_step="start",
        error=None
    )
