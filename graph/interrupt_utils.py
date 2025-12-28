"""
Human Interrupt Utilities

LangGraph 공식 휴먼 인터럽트 패턴을 위한 유틸리티 모듈입니다.

사용 예시 (향후 적용):
    from graph.interrupt_utils import create_interrupt_payload, handle_user_response
    
    def option_pause_node(state):
        payload = create_interrupt_payload(state)
        resp = interrupt(payload)  # LangGraph의 interrupt() 호출
        return handle_user_response(state, resp)
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class InterruptPayload:
    """휴먼 인터럽트 페이로드 구조"""
    question: str
    options: List[Dict[str, str]]
    interrupt_type: str  # "option_select", "text_input", "file_upload", "confirmation"
    metadata: Optional[Dict[str, Any]] = None


def create_interrupt_payload(
    question: str,
    options: List[Dict[str, str]] = None,
    interrupt_type: str = "option_select",
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    휴먼 인터럽트를 위한 페이로드를 생성합니다.
    
    Args:
        question: 사용자에게 보여줄 질문
        options: 선택 옵션 리스트 [{"title": "...", "description": "..."}, ...]
        interrupt_type: 인터럽트 유형
        metadata: 추가 메타데이터
        
    Returns:
        dict: interrupt()에 전달할 페이로드
        
    Example:
        payload = create_interrupt_payload(
            question="어떤 유형의 앱을 만들고 싶으신가요?",
            options=[
                {"title": "웹 서비스", "description": "브라우저 기반 SaaS"},
                {"title": "모바일 앱", "description": "iOS/Android 앱"}
            ],
            interrupt_type="option_select"
        )
        resp = interrupt(payload)
    """
    return {
        "question": question,
        "options": options or [],
        "interrupt_type": interrupt_type,
        "metadata": metadata or {},
        "__interrupt__": True  # 프론트엔드에서 인터럽트 감지용 마커
    }


def create_option_interrupt(state) -> Dict[str, Any]:
    """
    PlanCraftState에서 옵션 선택 인터럽트 페이로드를 생성합니다.
    
    Args:
        state: PlanCraftState 인스턴스
        
    Returns:
        dict: interrupt() 페이로드
    """
    question = getattr(state, "option_question", "추가 정보가 필요합니다.")
    options = getattr(state, "options", [])
    
    # 옵션을 표준 형식으로 변환
    formatted_options = []
    for opt in options:
        if isinstance(opt, dict):
            formatted_options.append({
                "title": opt.get("title", ""),
                "description": opt.get("description", "")
            })
        elif hasattr(opt, "title") and hasattr(opt, "description"):
            formatted_options.append({
                "title": opt.title,
                "description": opt.description
            })
    
    return create_interrupt_payload(
        question=question,
        options=formatted_options,
        interrupt_type="option_select",
        metadata={
            "user_input": getattr(state, "user_input", ""),
            "need_more_info": getattr(state, "need_more_info", False)
        }
    )


def handle_user_response(state, response: Dict[str, Any]):
    """
    사용자 응답(Command resume)을 처리하여 상태를 업데이트합니다.
    
    Args:
        state: 현재 PlanCraftState
        response: 사용자 응답 데이터
            {
                "selected_option": {"title": "...", "description": "..."},
                "text_input": "...",  # 직접 입력한 경우
            }
            
    Returns:
        PlanCraftState: 업데이트된 상태
    """
    selected = response.get("selected_option")
    text_input = response.get("text_input")
    
    # 새 입력 구성
    original_input = getattr(state, "user_input", "")
    
    if selected:
        title = selected.get("title", "")
        description = selected.get("description", "")
        new_input = f"{original_input}\n\n[선택: {title} - {description}]"
    elif text_input:
        new_input = f"{original_input}\n\n[직접 입력: {text_input}]"
    else:
        new_input = original_input
    
    # 상태 업데이트 (Immutable)
    return state.model_copy(update={
        "user_input": new_input,
        "need_more_info": False,
        "options": [],
        "option_question": None
    })


# =============================================================================
# 인터럽트 유형별 핸들러 (향후 확장용)
# =============================================================================

INTERRUPT_HANDLERS = {
    "option_select": lambda state, resp: handle_user_response(state, {"selected_option": resp}),
    "text_input": lambda state, resp: handle_user_response(state, {"text_input": resp}),
    "confirmation": lambda state, resp: state.model_copy(update={"confirmed": resp}),
    "file_upload": lambda state, resp: state.model_copy(update={"uploaded_content": resp}),
}


def get_interrupt_handler(interrupt_type: str):
    """인터럽트 유형에 맞는 핸들러를 반환합니다."""
    return INTERRUPT_HANDLERS.get(interrupt_type, handle_user_response)


# =============================================================================
# 사용 예시 (주석 처리된 미래 코드)
# =============================================================================
"""
향후 LangGraph interrupt 패턴 적용 시:

from langgraph.types import interrupt, Command

def option_pause_node(state: PlanCraftState) -> PlanCraftState:
    '''
    휴먼 인터럽트 노드 (옵션 선택 대기)
    
    이 노드가 실행되면:
    1. interrupt()로 실행이 중단됨
    2. UI에서 사용자가 옵션 선택 또는 직접 입력
    3. Command(resume=user_response)로 재시작
    4. 사용자 응답이 이 노드에 전달됨
    '''
    # 인터럽트 페이로드 생성
    payload = create_option_interrupt(state)
    
    # 실행 중단 & 사용자 응답 대기
    user_response = interrupt(payload)
    
    # 사용자 응답 처리
    return handle_user_response(state, user_response)


# 워크플로우에서:
workflow.add_node("option_pause", option_pause_node)
workflow.add_conditional_edges(
    "analyze",
    should_ask_user,
    {
        "ask_user": "option_pause",  # END 대신 interrupt 노드로
        "continue": "structure"
    }
)
"""
