"""
Human Interrupt Utilities

LangGraph 공식 휴먼 인터럽트 패턴을 위한 유틸리티 모듈입니다.

✅ 현재 상태: 활성화 (Active)
========================================
Analyzer에서 `need_more_info: true` 반환 시
Human Interrupt가 발생하여 사용자의 추가 입력을 대기합니다.

- Resume 시 Pydantic 검증을 통해 입력 데이터의 무결성을 보장합니다.
"""

from typing import Dict, List, Any, Optional, cast
from utils.schemas import OptionChoice, ResumeInput
from graph.state import PlanCraftState, InterruptPayload, InterruptOption

def create_interrupt_payload(
    question: str,
    options: List[OptionChoice] = None,
    input_schema_name: str = None,
    interrupt_type: str = "option",  # "option", "form", "confirm"
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    휴먼 인터럽트 페이로드 생성 (TypedDict 반환)
    """
    # OptionChoice(Pydantic) -> InterruptOption(TypedDict) 변환
    formatted_options: List[InterruptOption] = []
    if options:
        for opt in options:
            formatted_options.append({
                "title": opt.title,
                "description": opt.description
            })

    payload: InterruptPayload = {
        "type": interrupt_type,
        "question": question,
        "options": formatted_options,
        "input_schema_name": input_schema_name,
        "data": metadata or {}
    }
    
    return payload


def create_option_interrupt(state: PlanCraftState) -> Dict[str, Any]:
    """
    PlanCraftState에서 인터럽트 페이로드를 생성합니다.
    """
    question = state.get("option_question") or "추가 정보가 필요합니다."
    options = state.get("options", [])
    input_schema = state.get("input_schema_name")
    
    interrupt_type = "form" if input_schema else "option"
    
    # state.options는 [OptionChoice] (Pydantic) 일 수도 있고 [dict] 일 수도 있음
    # OptionChoice(Pydantic) 리스트로 정규화
    normalized_options: List[OptionChoice] = []
    
    for opt in options:
        if isinstance(opt, dict):
            normalized_options.append(OptionChoice(
                title=opt.get("title", ""),
                description=opt.get("description", "")
            ))
        elif hasattr(opt, "title") and hasattr(opt, "description"):
            # OptionChoice object via duck typing check
            normalized_options.append(OptionChoice(
                title=opt.title,
                description=opt.description
            ))
    
    return create_interrupt_payload(
        question=question,
        options=normalized_options,
        input_schema_name=input_schema,
        interrupt_type=interrupt_type,
        metadata={
            "user_input": state.get("user_input", ""),
            "need_more_info": state.get("need_more_info", False)
        }
    )

def handle_user_response(state: PlanCraftState, response: Dict[str, Any]) -> PlanCraftState:
    """
    사용자 응답(Command resume)을 처리하여 상태를 업데이트합니다.
    """
    from graph.state import update_state

    # 0. [NEW] 입력 유효성 검증 (Pydantic Guard)
    # 폼 데이터가 아닌 경우에만 ResumeInput 스키마 검증 수행
    if not state.get("input_schema_name"):
        try:
            # Pydantic 모델로 변환하여 검증 (실패 시 예외 발생)
            validated = ResumeInput(**response)
            # 검증된 데이터를 dict로 변환하여 사용 (타입 안전성 확보)
            response = validated.model_dump(exclude_unset=True)
            print(f"[HITL] Resume Input Validated: {response}")
        except Exception as e:
            print(f"[ERROR] Resume Input Validation Failed: {e}")
            # 검증 실패 시에도 흐름을 끊지 않고 원본 데이터를 사용하거나(로깅용),
            # 필요한 경우 에러 처리를 할 수 있음. 여기서는 경고만 출력.

    # 1. 폼 데이터 처리 (input_schema_name이 있었던 경우)
    if state.get("input_schema_name") and isinstance(response, dict):
        form_summary = "\n".join([f"- {k}: {v}" for k, v in response.items()])
        original_input = state.get("user_input", "")
        new_input = f"{original_input}\n\n[추가 정보 입력]\n{form_summary}"
        
        return update_state(
            state,
            user_input=new_input,
            need_more_info=False,
            input_schema_name=None
        )

    # 2. 옵션 선택 처리
    selected = response.get("selected_option")
    text_input = response.get("text_input")
    
    original_input = state.get("user_input", "")
    
    if selected:
        # Pydantic 모델 덤프 후 dict가 됨
        title = selected.get("title", "")
        description = selected.get("description", "")
        new_input = f"{original_input}\n\n[선택: {title} - {description}]"
    elif text_input:
        new_input = f"{original_input}\n\n[직접 입력: {text_input}]"
    else:
        new_input = original_input
    
    return update_state(
        state,
        user_input=new_input,
        need_more_info=False,
        options=[],
        option_question=None
    )


# =============================================================================
# 인터럽트 유형별 핸들러 (Update State Helper 사용)
# =============================================================================
from graph.state import update_state

INTERRUPT_HANDLERS = {
    "option_select": lambda state, resp: handle_user_response(state, {"selected_option": resp}),
    "text_input": lambda state, resp: handle_user_response(state, {"text_input": resp}),
    "confirmation": lambda state, resp: update_state(state, confirmed=resp),
    "file_upload": lambda state, resp: update_state(state, uploaded_content=resp),
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
