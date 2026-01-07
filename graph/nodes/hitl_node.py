"""
Human-in-the-Loop (HITL) Nodes

Version: 2.0.0
Last Updated: 2025-01-07
Author: PlanCraft Team

Changelog:
- v2.0.0 (2025-01-07): Dynamic interrupt() 패턴으로 전환 (LangGraph Best Practice)
- v1.0.0 (2025-01-06): interrupt_before 패턴 (Static)

Description:
[LangGraph Best Practice] Dynamic interrupt() 사용
- 노드 내부에서 조건부로 interrupt() 호출
- 더 유연한 HITL 로직 구현 가능
- 공식 권장: "Dynamic interrupts are recommended for HITL workflows"

⚠️ INTERRUPT SAFETY WARNING:
Resume 시 노드 전체가 처음부터 재실행됩니다!
- interrupt() 호출 전: Side-Effect 금지 (DB 저장, API 호출)
- interrupt() 호출 후: 안전하게 상태 변경 가능
"""
from typing import Literal, Any

try:
    from langgraph.types import Command, interrupt
except ImportError:
    # Fallback for older LangGraph versions
    class Command:
        def __init__(self, update=None, goto=None):
            self.update = update
            self.goto = goto

    def interrupt(value: Any) -> Any:
        raise NotImplementedError("interrupt() requires langgraph.types")

from graph.state import PlanCraftState, update_state
from graph.interrupt_utils import handle_user_response, create_option_interrupt
from utils.file_logger import get_file_logger


def option_pause_node(state: PlanCraftState) -> Command[Literal["analyze", "structure"]]:
    """
    HITL 처리 노드 (Dynamic interrupt 패턴)

    [동작 방식 - Dynamic Interrupt]
    1. analyze → should_ask_user → option_pause로 라우팅
    2. 이 노드에서 interrupt() 직접 호출 (payload와 함께)
    3. LangGraph가 실행 중단, 상태 저장
    4. API가 __interrupt__ 필드에서 payload 추출하여 반환
    5. 사용자가 옵션 선택 또는 텍스트 입력
    6. Command(resume=response)로 재개
    7. interrupt()가 사용자 응답을 반환
    8. 응답 처리 후 다음 노드로 이동

    ⚠️ Side-Effect 규칙:
    - interrupt() 전: 순수 함수만 (payload 생성)
    - interrupt() 후: Side-Effect 허용 (상태 업데이트)

    Args:
        state: 현재 워크플로우 상태

    Returns:
        Command: 다음 노드로 이동 (analyze 또는 structure)
    """
    logger = get_file_logger()

    # =========================================================================
    # [Phase 1] interrupt() 전 - Side-Effect 금지! (순수 함수만)
    # =========================================================================

    # Interrupt Payload 생성 (순수 함수)
    import uuid
    interrupt_id = str(uuid.uuid4())[:8]

    payload = create_option_interrupt(state, interrupt_id)
    logger.info(f"[HITL] Dynamic interrupt 호출: {payload.get('question', '')[:50]}...")

    # =========================================================================
    # [Phase 2] interrupt() 호출 - 여기서 실행 중단
    # =========================================================================

    # interrupt()는 사용자 응답을 반환 (Resume 시)
    user_response = interrupt(payload)

    # =========================================================================
    # [Phase 3] interrupt() 후 - Side-Effect 허용
    # =========================================================================

    logger.info(f"[HITL] Resume 수신: {type(user_response)}")

    # 사용자 응답 처리
    if isinstance(user_response, dict):
        updated_state = handle_user_response(state, user_response)

        # 사용자가 "자동 진행" 선택한 경우
        selected = user_response.get("selected_option", {})
        if isinstance(selected, dict):
            title = selected.get("title", "")
            if "AI가 알아서" in title or "진행" in title or "네" in title:
                logger.info("[HITL] 사용자 선택: 자동 진행 → structure")
                final_state = update_state(
                    updated_state,
                    need_more_info=False,
                    options=[],
                    option_question=None
                )
                return Command(update=final_state, goto="structure")

        # 기본: 새 정보로 다시 분석
        logger.info("[HITL] Resume 완료 → analyze 재실행")
        final_state = update_state(
            updated_state,
            need_more_info=False,
            options=[],
            option_question=None
        )
        return Command(update=final_state, goto="analyze")

    # Fallback: 응답이 없거나 형식이 다른 경우
    logger.warning(f"[HITL] 예상치 못한 응답 형식: {user_response}")
    fallback_state = update_state(
        state,
        need_more_info=False,
        options=[],
        option_question=None
    )
    return Command(update=fallback_state, goto="analyze")
