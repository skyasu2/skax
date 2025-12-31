"""
Human Interrupt Utilities

LangGraph 공식 휴먼 인터럽트 패턴을 위한 유틸리티 모듈입니다.

✅ 현재 상태: 활성화 (Active)
========================================
Analyzer에서 `need_more_info: true` 반환 시
Human Interrupt가 발생하여 사용자의 추가 입력을 대기합니다.

- Resume 시 Pydantic 검증을 통해 입력 데이터의 무결성을 보장합니다.

모듈 구조:
    - interrupt_types.py: 타입 안전한 Payload 클래스들 (Pydantic 기반)
    - interrupt_utils.py: 기존 코드 호환 유틸리티 + State 연동 함수

권장 사용법 (신규 코드):
    from graph.interrupt_types import InterruptFactory, InterruptType

    payload = InterruptFactory.create(InterruptType.OPTION, question="선택하세요", ...)

기존 코드 호환:
    from graph.interrupt_utils import create_option_interrupt, handle_user_response
"""

from typing import Dict, List, Any, Optional, cast
from utils.schemas import OptionChoice, ResumeInput
from graph.state import PlanCraftState, InterruptPayload, InterruptOption

# [NEW] 모듈화된 인터럽트 타입 시스템 임포트
from graph.interrupt_types import (
    InterruptType,
    InterruptFactory,
    ResumeHandler,
    BaseInterruptPayload,
    OptionInterruptPayload,
    FormInterruptPayload,
    ConfirmInterruptPayload,
    ApprovalInterruptPayload,
    InterruptOption as TypedInterruptOption,
    normalize_options,  # [NEW] 옵션 정규화 유틸리티
)

def _format_resume_summary(response: Dict[str, Any]) -> str:
    """Resume 응답을 사람이 읽기 쉬운 요약으로 변환"""
    selected = response.get("selected_option")
    text_input = response.get("text_input")

    if selected:
        title = selected.get("title", "") if isinstance(selected, dict) else str(selected)
        return f"옵션 선택: {title}"
    elif text_input:
        # 긴 텍스트는 잘라서 표시
        preview = text_input[:50] + "..." if len(str(text_input)) > 50 else text_input
        return f"직접 입력: {preview}"
    else:
        return "응답 없음 (기본값 사용)"


def _sanitize_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """민감 정보를 제거한 응답 사본 반환 (로깅용)"""
    sanitized = {}
    for key, value in response.items():
        # 민감할 수 있는 키는 마스킹
        if key in ("password", "secret", "token", "api_key"):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, str) and len(value) > 200:
            # 너무 긴 텍스트는 잘라서 저장
            sanitized[key] = value[:200] + "...(truncated)"
        else:
            sanitized[key] = value
    return sanitized


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

    [UPDATE] normalize_options()를 사용하여 다양한 형태의 옵션을
    일관된 형식으로 변환합니다. (dict, Pydantic, duck-typing 모두 지원)
    """
    question = state.get("option_question") or "추가 정보가 필요합니다."
    options = state.get("options", [])
    input_schema = state.get("input_schema_name")

    interrupt_type = "form" if input_schema else "option"

    # [UPDATE] normalize_options 유틸리티 사용 (일관성 보장)
    # TypedInterruptOption → OptionChoice 변환
    typed_options = normalize_options(options)
    normalized_options: List[OptionChoice] = [
        OptionChoice(title=opt.title, description=opt.description)
        for opt in typed_options
    ]

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

    [Best Practice] Resume 입력 내역을 step_history에 기록하여
    디버깅 및 리플레이 시 사용자 선택/입력을 추적할 수 있습니다.
    """
    from graph.state import update_state
    import time

    # =========================================================================
    # [NEW] Resume 입력 내역을 step_history에 기록 (디버깅/리플레이용)
    # =========================================================================
    resume_history_item = {
        "step": "human_resume",
        "status": "USER_INPUT",
        "summary": _format_resume_summary(response),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "response_data": _sanitize_response(response)  # 민감 정보 제거된 사본
    }

    current_history = state.get("step_history", []) or []
    updated_history = current_history + [resume_history_item]

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
            input_schema_name=None,
            step_history=updated_history  # [NEW] Resume 이력 포함
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
        selected_option=selected,  # [NEW] 선택 이력 저장 (분석용)
        need_more_info=False,
        options=[],
        option_question=None,
        step_history=updated_history  # [NEW] Resume 이력 포함
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


# 인터럽트 패턴 구현은 graph/workflow.py의 option_pause_node() 참조


# =============================================================================
# Pause Node Factory (LangGraph Best Practice 확장)
# =============================================================================

def make_pause_node(
    question: str,
    goto_node: str,
    interrupt_type: str = "option",
    options: List[Dict[str, str]] = None
):
    """
    범용 Pause Node 팩토리 함수.
    
    다양한 HITL 유형의 pause node를 한 줄로 생성할 수 있습니다.
    
    Args:
        question: 사용자에게 표시할 질문
        goto_node: 사용자 응답 후 이동할 노드 이름
        interrupt_type: 인터럽트 유형 ("option", "form", "confirm")
        options: 옵션 목록 (interrupt_type="option"일 때)
    
    Returns:
        Callable: LangGraph 노드 함수
    
    Example:
        workflow.add_node("confirm_structure", make_pause_node(
            question="이 구조로 진행할까요?",
            goto_node="write",
            interrupt_type="confirm"
        ))
    """
    from langgraph.types import interrupt, Command
    
    def pause_node(state: PlanCraftState):
        payload = {
            "type": interrupt_type,
            "question": question,
            "options": options or [],
            "data": {"user_input": state.get("user_input", "")}
        }
        
        user_response = interrupt(payload)
        updated_state = handle_user_response(state, user_response)
        
        return Command(update=updated_state, goto=goto_node)
    
    return pause_node


def make_approval_pause_node(
    role: str,
    question: str,
    goto_approved: str,
    goto_rejected: str,
    rejection_feedback_enabled: bool = True
):
    """
    역할 기반 승인 Pause Node 팩토리 함수.
    
    팀장/리더/QA 등 역할별 승인 워크플로우를 쉽게 구현할 수 있습니다.
    사용자의 승인/반려 응답에 따라 다른 노드로 분기합니다.
    
    Args:
        role: 승인자 역할 (예: "팀장", "리더", "QA")
        question: 승인 요청 질문
        goto_approved: 승인 시 이동할 노드
        goto_rejected: 반려 시 이동할 노드
        rejection_feedback_enabled: 반려 시 피드백 입력 활성화
    
    Returns:
        Callable: LangGraph 노드 함수
    
    Example:
        workflow.add_node("team_leader_approval", make_approval_pause_node(
            role="팀장",
            question="이 기획서를 승인하시겠습니까?",
            goto_approved="format",
            goto_rejected="refine"
        ))
    """
    from langgraph.types import interrupt, Command
    
    def approval_pause_node(state: PlanCraftState):
        payload = {
            "type": "approval",
            "role": role,
            "question": question,
            "options": [
                {"title": "✅ 승인", "value": "approve", "description": "진행합니다"},
                {"title": "🔄 반려", "value": "reject", "description": "수정이 필요합니다"}
            ],
            "rejection_feedback_enabled": rejection_feedback_enabled,
            "data": {
                "user_input": state.get("user_input", ""),
                "current_step": state.get("current_step", "")
            }
        }
        
        user_response = interrupt(payload)
        updated_state = handle_user_response(state, user_response)
        
        # 승인 여부에 따른 분기
        is_approved = user_response.get("approved", False)
        selected = user_response.get("selected_option", {})
        
        # selected_option.value가 "approve"면 승인
        if is_approved or selected.get("value") == "approve":
            return Command(update=updated_state, goto=goto_approved)
        else:
            # 반려 사유가 있으면 상태에 추가
            rejection_reason = user_response.get("rejection_reason", "")
            if rejection_reason:
                from graph.state import update_state
                updated_state = update_state(
                    updated_state,
                    rejection_reason=rejection_reason
                )
            return Command(update=updated_state, goto=goto_rejected)
    
    return approval_pause_node


def make_multi_approval_chain(approvers: List[Dict[str, str]], final_goto: str):
    """
    다중 승인 체인을 위한 노드 목록 생성.
    
    여러 승인자가 순차적으로 승인해야 하는 워크플로우를 구성합니다.
    
    Args:
        approvers: 승인자 목록 [{"role": "팀장", "question": "..."}, ...]
        final_goto: 모든 승인 후 이동할 노드
    
    Returns:
        Dict[str, Callable]: 노드 이름과 노드 함수의 딕셔너리
    
    Example:
        approval_nodes = make_multi_approval_chain(
            approvers=[
                {"role": "팀장", "question": "팀장 승인"},
                {"role": "리더", "question": "리더 승인"}
            ],
            final_goto="format"
        )
        for name, node in approval_nodes.items():
            workflow.add_node(name, node)
    """
    nodes = {}
    
    for i, approver in enumerate(approvers):
        role = approver.get("role", f"Approver_{i}")
        question = approver.get("question", f"{role} 승인이 필요합니다.")
        node_name = f"{role.lower()}_approval"
        
        # 다음 노드 결정 (마지막이면 final_goto, 아니면 다음 승인자)
        if i < len(approvers) - 1:
            next_role = approvers[i + 1].get("role", f"Approver_{i+1}")
            next_goto = f"{next_role.lower()}_approval"
        else:
            next_goto = final_goto
        
        nodes[node_name] = make_approval_pause_node(
            role=role,
            question=question,
            goto_approved=next_goto,
            goto_rejected="refine"  # 반려 시 항상 refine으로
        )

    return nodes


# =============================================================================
# Public API Export
# =============================================================================

__all__ = [
    # 기존 호환 함수
    "create_interrupt_payload",
    "create_option_interrupt",
    "handle_user_response",
    "get_interrupt_handler",
    "make_pause_node",
    "make_approval_pause_node",
    "make_multi_approval_chain",
    # 신규 모듈화 시스템 (re-export)
    "InterruptType",
    "InterruptFactory",
    "ResumeHandler",
    "BaseInterruptPayload",
    "OptionInterruptPayload",
    "FormInterruptPayload",
    "ConfirmInterruptPayload",
    "ApprovalInterruptPayload",
    # [NEW] 옵션 정규화 유틸리티
    "normalize_options",
]
