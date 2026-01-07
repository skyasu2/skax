"""
Human-in-the-Loop (HITL) Nodes

[LangGraph Best Practice] interrupt_before 사용
- 노드 내부 interrupt() 대신 compile 옵션으로 interrupt 지점 지정
- workflow.compile(interrupt_before=["option_pause"])로 설정됨
- 노드 실행 전에 자동으로 interrupt 발생, Resume 시 노드 실행
"""
from typing import Literal

try:
    from langgraph.types import Command
except ImportError:
    class Command:
        def __init__(self, update=None, goto=None):
            self.update = update
            self.goto = goto

from graph.state import PlanCraftState, update_state
from graph.interrupt_utils import handle_user_response
from utils.file_logger import get_file_logger


def option_pause_node(state: PlanCraftState) -> Command[Literal["analyze", "structure"]]:
    """
    HITL 처리 노드 (interrupt_before 패턴)

    [동작 방식]
    1. analyze → should_ask_user → option_pause로 라우팅
    2. interrupt_before에 의해 노드 실행 전 interrupt 발생
    3. API가 interrupt payload 반환 (options, question 등)
    4. 사용자가 옵션 선택 또는 텍스트 입력
    5. Resume 시 이 노드가 실행됨
    6. 사용자 응답 처리 후 analyze로 이동 (재분석)

    Args:
        state: 현재 워크플로우 상태
            - __interrupt_resume__: Resume 시 전달된 사용자 응답

    Returns:
        Command: 다음 노드로 이동 (analyze 또는 structure)
    """
    logger = get_file_logger()

    # Resume 데이터 확인 (Command(resume=...) 로 전달된 값)
    # LangGraph는 resume 값을 state의 특정 위치에 넣거나 별도로 전달
    # 여기서는 run_plancraft에서 resume_command를 처리하므로
    # state에서 selected_option 또는 user_input 변경사항을 확인

    # 사용자가 "직접 입력"을 선택한 경우 처리
    selected = state.get("selected_option")
    if selected and isinstance(selected, dict):
        title = selected.get("title", "")
        if "AI가 알아서" in title or "진행" in title:
            # 자동 진행 선택 - 구조화 단계로 이동
            logger.info("[HITL] 사용자 선택: 자동 진행 → structure")
            updated = update_state(
                state,
                need_more_info=False,
                options=[],
                option_question=None
            )
            return Command(update=updated, goto="structure")

    # 기본: 새 정보로 다시 분석
    logger.info("[HITL] Resume 완료 → analyze 재실행")
    updated = update_state(
        state,
        need_more_info=False,
        options=[],
        option_question=None
    )
    return Command(update=updated, goto="analyze")
