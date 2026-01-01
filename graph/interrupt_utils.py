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
from enum import Enum
from utils.schemas import OptionChoice, ResumeInput
from graph.state import PlanCraftState, InterruptPayload, InterruptOption


# =============================================================================
# HITL 이벤트 라벨 (운영 로그/감사 추적용)
# =============================================================================

class HITLEventLabel(str, Enum):
    """
    Human-in-the-Loop 이벤트 라벨

    운영 로그와 감사 추적에서 HITL 이벤트를 명확히 식별합니다.

    Labels:
        PAUSE_OPTION: 옵션 선택 대기
        PAUSE_FORM: 폼 입력 대기
        PAUSE_CONFIRM: 확인 대기
        PAUSE_APPROVAL: 승인 대기
        RESUME_SELECT: 옵션 선택 완료
        RESUME_INPUT: 텍스트 입력 완료
        RESUME_APPROVE: 승인 완료
        RESUME_REJECT: 반려 완료
        TIMEOUT: 입력 시간 만료
        RETRY: 재입력 요청

    Example:
        >>> event = {"label": HITLEventLabel.RESUME_SELECT, "data": {...}}
        >>> if event["label"] == HITLEventLabel.RESUME_APPROVE:
        ...     print("승인 처리")
    """
    # Pause Events (인터럽트 발생)
    PAUSE_OPTION = "HITL:PAUSE:OPTION"
    PAUSE_FORM = "HITL:PAUSE:FORM"
    PAUSE_CONFIRM = "HITL:PAUSE:CONFIRM"
    PAUSE_APPROVAL = "HITL:PAUSE:APPROVAL"

    # Resume Events (사용자 응답)
    RESUME_SELECT = "HITL:RESUME:SELECT"
    RESUME_INPUT = "HITL:RESUME:INPUT"
    RESUME_APPROVE = "HITL:RESUME:APPROVE"
    RESUME_REJECT = "HITL:RESUME:REJECT"

    # Special Events
    TIMEOUT = "HITL:TIMEOUT"
    RETRY = "HITL:RETRY"
    FALLBACK = "HITL:FALLBACK"


def get_hitl_event_label(pause_type: str, response: Dict[str, Any]) -> str:
    """
    응답 내용에 따른 HITL 이벤트 라벨 반환

    Args:
        pause_type: 인터럽트 타입 (option, form, confirm, approval)
        response: 사용자 응답 데이터

    Returns:
        str: HITL 이벤트 라벨

    Example:
        >>> get_hitl_event_label("option", {"selected_option": {...}})
        "HITL:RESUME:SELECT"
        >>> get_hitl_event_label("approval", {"approved": True})
        "HITL:RESUME:APPROVE"
    """
    # 승인/반려 처리
    if pause_type == "approval":
        if response.get("approved") or response.get("selected_option", {}).get("value") == "approve":
            return HITLEventLabel.RESUME_APPROVE.value
        return HITLEventLabel.RESUME_REJECT.value

    # 옵션 선택
    if response.get("selected_option"):
        return HITLEventLabel.RESUME_SELECT.value

    # 텍스트 입력
    if response.get("text_input"):
        return HITLEventLabel.RESUME_INPUT.value

    # Fallback
    if response.get("value") == "default_fallback":
        return HITLEventLabel.FALLBACK.value

    return f"HITL:RESUME:{pause_type.upper()}"

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
    interrupt_id: str,
    options: List[OptionChoice] = None,
    input_schema_name: str = None,
    interrupt_type: str = "option",
    metadata: Dict[str, Any] = None,
    node_ref: str = "unknown_node"
) -> Dict[str, Any]:
    """
    [Legacy Wrapper] hitl_config.py의 표준 함수로 위임
    """
    from graph.hitl_config import create_base_payload, InterruptType
    
    # 딕셔너리 변환 (Pydantic 호환)
    opt_dicts = []
    if options:
        for opt in options:
            opt_dicts.append({"title": opt.title, "description": opt.description})

    return create_base_payload(
        interrupt_type=InterruptType(interrupt_type),
        question=question,
        node_ref=node_ref,
        interrupt_id=interrupt_id,
        options=opt_dicts,
        input_schema_name=input_schema_name,

        data=metadata or {},
        # [NEW] Snapshot from metadata if available (Legacy Wrapper limitation)
        snapshot=metadata.get("snapshot") if metadata else None
    )


def create_option_interrupt(state: PlanCraftState, interrupt_id: str) -> Dict[str, Any]:
    """
    PlanCraftState에서 인터럽트 페이로드를 생성합니다.
    """
    from graph.hitl_config import create_option_payload, create_form_payload
    
    question = state.get("option_question") or "추가 정보가 필요합니다."
    
    # [NEW] Form 타입 처리 (input_schema_name 존재 시)
    input_schema_name = state.get("input_schema_name")
    if input_schema_name:
        return create_form_payload(
            question=question,
            input_schema_name=input_schema_name,

            node_ref="option_pause_node",
            interrupt_id=interrupt_id,
            retry_count=state.get("retry_count", 0), # [Fix] Pass top-level for hint generation
            data={
                "user_input": state.get("user_input", ""),
                "need_more_info": state.get("need_more_info", False),
                "retry_count": state.get("retry_count", 0),

            },
            # [NEW] Snapshot
            snapshot={
                "user_input": state.get("user_input"),
                "current_step": state.get("current_step"),
                "retry_count": state.get("retry_count"),
            }
        )
    options = state.get("options", [])
    
    # [UPDATE] normalize_options 사용
    typed_options = normalize_options(options)
    opt_dicts = [{"title": opt.title, "description": opt.description} for opt in typed_options]

    return create_option_payload(
        question=question,
        options=opt_dicts,
        node_ref="option_pause_node", # 호출부에서 넘겨받으면 좋겠지만 workflow 구조상 고정
        interrupt_id=interrupt_id,
        retry_count=state.get("retry_count", 0), # [Fix] Pass top-level for hint generation
        data={
            "user_input": state.get("user_input", ""),
            "need_more_info": state.get("need_more_info", False),
            "retry_count": state.get("retry_count", 0),
        },
        # [NEW] Snapshot
        snapshot={
            "user_input": state.get("user_input"),
            "current_step": state.get("current_step"),
            "retry_count": state.get("retry_count"),
        }
    )

def handle_user_response(state: PlanCraftState, response: Dict[str, Any]) -> PlanCraftState:
    """
    사용자 응답(Command resume)을 처리하여 상태를 업데이트합니다.

    [Best Practice] Resume 입력 내역을 step_history에 기록하여
    디버깅 및 리플레이 시 사용자 선택/입력을 추적할 수 있습니다.

    HITL 메타필드 기록:
        - last_pause_type: 마지막 인터럽트 타입
        - last_resume_value: 사용자 응답값 (민감정보 제거)
        - last_human_event: 전체 HITL 이벤트 정보

    Args:
        state: 현재 PlanCraftState
        response: 사용자 응답 (UI에서 전달)

    Returns:
        업데이트된 PlanCraftState

    Response Input Schema (Option Select):
        ```json
        {
            "selected_option": {
                "title": "웹 애플리케이션",
                "description": "브라우저 기반 서비스"
            }
        }
        ```

    Response Input Schema (Text Input):
        ```json
        {
            "text_input": "AI 기반 헬스케어 앱을 만들고 싶습니다"
        }
        ```

    Response Input Schema (Approval):
        ```json
        {
            "approved": true,
            "selected_option": {"title": "승인", "value": "approve"}
        }
        ```

    step_history Record Schema (자동 기록):
        ```json
        {
            "step": "human_resume",
            "status": "USER_INPUT",
            "summary": "옵션 선택: 웹 애플리케이션",
            "timestamp": "2024-01-15 14:30:00",
            "event_type": "HUMAN_RESPONSE",
            "pause_type": "option",
            "response_data": {"selected_option": {...}},
            "last_interrupt_payload": {...}
        }
        ```

    last_human_event Schema (State 메타필드):
        ```json
        {
            "event_type": "HITL_RESUME",
            "pause_type": "option",
            "resume_value": {"selected_option": {...}},
            "timestamp": "2024-01-15 14:30:00",
            "node_ref": "option_pause",
            "event_id": "evt_abc123"
        }
        ```
    """
    from graph.state import update_state
    import time
    from datetime import datetime  # [NEW]

    # =========================================================================
    # [NEW] 인터럽트 타입 추출 (last_interrupt에서 가져오거나 기본값)
    # =========================================================================
    last_interrupt = state.get("last_interrupt") or {}
    
    # [NEW] 만료(Timeout) 체크
    if last_interrupt.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(last_interrupt["expires_at"])
            if datetime.now() > expires_at:
                print(f"[HITL] Interrupt Expired! (Event ID: {last_interrupt.get('event_id')})")
                # 만료 시 에러 상태 반환 (User에게 재시도 요청 또는 종료 유도)
                return update_state(state, error="Time Limit Exceeded: 입력 시간이 만료되었습니다.")
        except Exception as e:
            print(f"[ERROR] Expiry Check Failed: {e}")

    pause_type = last_interrupt.get("type", "option")  # 기본값: option
    current_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # [ENHANCED] HITL 이벤트 라벨 생성 (운영 로그용)
    hitl_label = get_hitl_event_label(pause_type, response)

    # =========================================================================
    # [NEW] Resume 입력 내역을 step_history에 기록 (디버깅/리플레이용)
    # =========================================================================
    resume_history_item = {
        "step": "human_resume",
        "status": "USER_INPUT",
        "summary": _format_resume_summary(response),
        "timestamp": current_timestamp,
        "response_data": _sanitize_response(response),  # 민감 정보 제거된 사본
        "event_type": "HUMAN_RESPONSE",  # [NEW] 이벤트 타입 명시
        "hitl_label": hitl_label,  # [ENHANCED] 명시적 HITL 라벨 (HITL:RESUME:SELECT 등)
        "pause_type": pause_type,  # [NEW] 인터럽트 타입 기록
        # [NEW] 직전 인터럽트 정보 백업 (추적용)
        "last_interrupt_payload": last_interrupt,
        # [NEW] Audit Trail including task context
        "audit_trail": {
            "task_step": state.get("current_step"),
            "interrupt_id": last_interrupt.get("interrupt_id"),
            "node_ref": last_interrupt.get("node_ref"),
            "event_id": last_interrupt.get("event_id"),
        }
    }

    # =========================================================================
    # [NEW] HITL 메타필드 구성 (운영/디버깅/감사용)
    # =========================================================================
    last_human_event = {
        "event_type": "HITL_RESUME",
        "hitl_label": hitl_label,  # [ENHANCED] 명시적 라벨
        "pause_type": pause_type,
        "resume_value": _sanitize_response(response),
        "timestamp": current_timestamp,
        "node_ref": last_interrupt.get("node_ref"),
        "event_id": last_interrupt.get("event_id"),
    }

    # [NEW] Update Phase 6 Task
    # TODO: This logic should ideally be in the task boundary, but marking progress here
    
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
            step_history=updated_history,  # [NEW] Resume 이력 포함
            # [NEW] HITL 메타필드 기록
            last_pause_type=pause_type,
            last_resume_value=_sanitize_response(response),
            last_human_event=last_human_event,
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
        step_history=updated_history,  # [NEW] Resume 이력 포함
        # [NEW] HITL 메타필드 기록
        last_pause_type=pause_type,
        last_resume_value=_sanitize_response(response),
        last_human_event=last_human_event,
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

    Approval Flow Diagram:
    ```mermaid
    stateDiagram-v2
        [*] --> ApprovalNode: interrupt()
        ApprovalNode --> WaitingForUser: Pause

        state WaitingForUser {
            [*] --> ShowOptions
            ShowOptions --> UserDecision
        }

        WaitingForUser --> Approved: value="approve"
        WaitingForUser --> Rejected: value="reject"

        Approved --> goto_approved: Command(goto=approved_node)
        Rejected --> goto_rejected: Command(goto=rejected_node)

        note right of Rejected
            rejection_reason이
            State에 기록됨
        end note
    ```

    | 승인 여부 | User Response (Value) | 이동 경로 | 비고 |
    |---|---|---|---|
    | 승인 | `approve` or `approved=True` | `goto_approved` | 다음 단계 진행 |
    | 반려 | `reject` | `goto_rejected` | 상태에 `rejection_reason` 기록 |

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

    Multi-Approval Chain Diagram:
    ```mermaid
    flowchart LR
        subgraph ApprovalChain["다중 승인 체인"]
            A[팀장_approval] -->|approve| B[리더_approval]
            B -->|approve| C[QA_approval]
            C -->|approve| D[final_goto]

            A -->|reject| R[refine]
            B -->|reject| R
            C -->|reject| R
        end

        style A fill:#e1f5fe
        style B fill:#e1f5fe
        style C fill:#e1f5fe
        style D fill:#c8e6c9
        style R fill:#ffcdd2
    ```

    Entry/Exit Conditions:
    ```
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      Multi-Approval Chain Flow                          │
    ├─────────────┬───────────────────────────────────────────────────────────┤
    │ 진입 조건   │ 이전 노드에서 승인 체인으로 라우팅                         │
    ├─────────────┼───────────────────────────────────────────────────────────┤
    │ 승인 시     │ 다음 승인자로 이동 (마지막이면 final_goto)                 │
    ├─────────────┼───────────────────────────────────────────────────────────┤
    │ 반려 시     │ 항상 "refine" 노드로 이동 (rejection_reason 기록)          │
    ├─────────────┼───────────────────────────────────────────────────────────┤
    │ 종료 조건   │ 모든 승인자가 승인 → final_goto 노드로 이동               │
    └─────────────┴───────────────────────────────────────────────────────────┘
    ```

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
# Pause State 초기화 유틸리티 (Resume 완료 후 정리)
# =============================================================================

def reset_pause_state() -> Dict[str, Any]:
    """
    Pause 관련 상태 필드를 초기화합니다.

    Resume 완료 후 다음 Pause를 위해 상태를 정리합니다.
    이 함수의 반환값을 update_state()에 spread하여 사용합니다.

    Returns:
        초기화할 필드들의 딕셔너리

    Usage:
        from graph.interrupt_utils import reset_pause_state
        new_state = update_state(state, **reset_pause_state())

    Note:
        - last_resume_value, last_human_event는 감사 추적용으로 유지됨
        - step_history는 누적되므로 초기화하지 않음
    """
    return {
        # Interrupt 메타데이터 초기화
        "last_interrupt": None,
        "last_pause_type": None,

        # 옵션 선택 관련 (다음 Pause를 위해 비움)
        "options": [],
        "option_question": None,

        # 에러 상태 초기화
        "error": None,
        "error_category": None,
        "last_error": None,
    }


def get_pause_state_checklist(state: PlanCraftState) -> Dict[str, Any]:
    """
    현재 Pause 관련 상태를 점검합니다.

    디버깅 및 Resume 전 상태 확인용입니다.

    Returns:
        Pause 관련 필드들의 현재 값
    """
    return {
        "has_pending_interrupt": state.get("last_interrupt") is not None,
        "last_pause_type": state.get("last_pause_type"),
        "options_count": len(state.get("options", [])),
        "has_question": state.get("option_question") is not None,
        "has_error": state.get("error") is not None,
        "last_resume_value": state.get("last_resume_value"),
    }


def validate_resume_readiness(state: PlanCraftState) -> tuple[bool, List[str]]:
    """
    Resume 준비 상태를 검증합니다.

    Resume 전에 호출하여 상태가 올바른지 확인합니다.

    Returns:
        (is_ready, errors): 준비 완료 여부와 에러 목록

    Usage:
        is_ready, errors = validate_resume_readiness(state)
        if not is_ready:
            raise StateError(f"Resume 불가: {errors}")
    """
    errors = []

    # 필수 필드 확인
    if not state.get("user_input"):
        errors.append("user_input 누락")

    if not state.get("thread_id"):
        errors.append("thread_id 누락")

    # 카운터 범위 검증
    from utils.settings import settings
    refine_count = state.get("refine_count", 0)
    if refine_count > settings.MAX_REFINE_LOOPS:
        errors.append(f"refine_count 초과: {refine_count} > {settings.MAX_REFINE_LOOPS}")

    restart_count = state.get("restart_count", 0)
    if restart_count > settings.MAX_RESTART_COUNT:
        errors.append(f"restart_count 초과: {restart_count} > {settings.MAX_RESTART_COUNT}")

    return (len(errors) == 0, errors)


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
    # [ENHANCED] HITL 이벤트 라벨
    "HITLEventLabel",
    "get_hitl_event_label",
    # [NEW] Pause State 초기화 유틸리티
    "reset_pause_state",
    "get_pause_state_checklist",
    "validate_resume_readiness",
]
