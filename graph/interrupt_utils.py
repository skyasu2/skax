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
from utils.schemas import InterruptPayload, OptionChoice, PlanCraftState

def create_interrupt_payload(
    question: str,
    options: List[OptionChoice] = None,
    input_schema_name: str = None,
    interrupt_type: str = "option",  # "option", "form", "confirm"
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    휴먼 인터럽트 페이로드 생성 (Pydantic 모델 -> Dict 변환)
    """
    payload = InterruptPayload(
        type=interrupt_type,
        question=question,
        options=options or [],
        input_schema_name=input_schema_name,
        data=metadata or {}
    )
    # LangGraph interrupt()는 JSON serializable 객체를 기대하므로 dict로 반환
    return payload.model_dump()


def create_option_interrupt(state: PlanCraftState) -> Dict[str, Any]:
    """
    PlanCraftState에서 인터럽트 페이로드를 생성합니다.
    - input_schema_name이 있으면 'form' 타입
    - options가 있으면 'option' 타입
    """
    question = getattr(state, "option_question", "추가 정보가 필요합니다.") or "추가 정보가 필요합니다."
    options = getattr(state, "options", [])
    input_schema = getattr(state, "input_schema_name", None)
    
    interrupt_type = "form" if input_schema else "option"
    
    # 옵션 데이터 정규화 (Dict or OptionChoice -> OptionChoice)
    formatted_options = []
    for opt in options:
        if isinstance(opt, dict):
            formatted_options.append(OptionChoice(
                title=opt.get("title", ""),
                description=opt.get("description", "")
            ))
        elif isinstance(opt, OptionChoice):
            formatted_options.append(opt)
        elif hasattr(opt, "title") and hasattr(opt, "description"):
            # Mock 객체 등 호환성
            formatted_options.append(OptionChoice(
                title=opt.title,
                description=opt.description
            ))
    
    return create_interrupt_payload(
        question=question,
        options=formatted_options,
        input_schema_name=input_schema,
        interrupt_type=interrupt_type,
        metadata={
            "user_input": getattr(state, "user_input", ""),
            "need_more_info": getattr(state, "need_more_info", False)
        }
    )


def handle_user_response(state: PlanCraftState, response: Dict[str, Any]) -> PlanCraftState:
    """
    사용자 응답(Command resume)을 처리하여 상태를 업데이트합니다.
    """
    # 1. 폼 데이터 처리 (input_schema_name이 있었던 경우)
    # response 자체가 폼 데이터 dict일 수 있음
    if state.input_schema_name and isinstance(response, dict):
        # 폼 데이터를 컨텍스트에 추가하는 방식으로 처리 (간단히 user_input에 추가)
        form_summary = "\n".join([f"- {k}: {v}" for k, v in response.items()])
        new_input = f"{state.user_input}\n\n[추가 정보 입력]\n{form_summary}"
        
        return state.model_copy(update={
            "user_input": new_input,
            "need_more_info": False,
            "input_schema_name": None # 초기화
        })

    # 2. 옵션 선택 처리
    selected = response.get("selected_option")
    text_input = response.get("text_input")
    
    original_input = state.user_input
    
    if selected:
        # selected가 dict형태로 옴
        title = selected.get("title", "")
        description = selected.get("description", "")
        new_input = f"{original_input}\n\n[선택: {title} - {description}]"
    elif text_input:
        new_input = f"{original_input}\n\n[직접 입력: {text_input}]"
    else:
        new_input = original_input
    
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
