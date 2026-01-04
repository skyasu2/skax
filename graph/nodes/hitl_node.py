"""
Human-in-the-Loop (HITL) Nodes
"""
import time
import uuid
from typing import Literal

try:
    from langgraph.types import interrupt, Command
except ImportError:
    # LangGraph 호환성 Mock
    def interrupt(value): return None
    class Command:
        def __init__(self, update=None, goto=None):
            self.update = update
            self.goto = goto

from graph.state import PlanCraftState, update_state
from graph.interrupt_utils import create_option_interrupt, handle_user_response
from utils.settings import settings
from utils.file_logger import get_file_logger

def option_pause_node(state: PlanCraftState) -> Command[Literal["analyze", "option_pause"]]:
    """
    휴먼 인터럽트 처리 노드 (LangGraph 공식 Best Practice 적용)

    Return Type: Command[Literal["analyze"]]
    - 사용자 응답 후 항상 analyze 노드로 이동

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    [LangGraph HITL Best Practice - 팀/후임자 필독]
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    1️⃣ interrupt 호출 순서/갯수 절대 고정
       - 이 노드의 interrupt() 호출 순서와 갯수는 절대 변경 금지
       - Resume 시 value는 호출 순서(0-base index)로 매칭됨
       - 동적으로 interrupt 갯수/순서 변경 시 Resume Mismatch 발생!

    2️⃣ Side-Effect는 interrupt() 이후에만
       - interrupt() 이전: 순수 로직만 (payload 생성, 조건 검사)
       - interrupt() 이후: Side-Effect 허용 (DB 저장, API 호출, 상태 변경)
       - 이유: Resume 시 interrupt() 이전 코드가 재실행됨

    3️⃣ Multi-Interrupt 사용 시 주의
       - 단일 노드 내 여러 interrupt() 호출 가능 (예: 유효성 검사 루프)
       - Resume values는 List[Any]로 전달되며, 호출 순서대로 인덱싱
       - 예: [interrupt_1_response, interrupt_2_response, ...]

    4️⃣ Subgraph 내 interrupt 시
       - 부모 노드/Subgraph 전체가 Resume 시 재실행될 수 있음
       - docs/HITL_GUIDE.md 참조

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ⚠️ CRITICAL: Resume 시 이 노드는 처음부터 다시 실행됩니다!
    - interrupt() 호출 이전의 모든 코드가 Resume 시 재실행됨
    - Side-Effect(DB 저장, API 호출, 알림 발송)는 반드시 interrupt() 이후에 배치
    - LLM 호출, 외부 API 호출은 interrupt() 전에 절대 금지

    💡 외부 시스템 연동 시 주의사항:
    - LangGraph checkpointer는 State만 복원하며, 외부 시스템(DB, Redis, 3rd-party API) 상태는 복원하지 않음
    - 외부 시스템과 연동하는 경우, interrupt() 호출 직전에 해당 상태를 State에 저장하거나
      별도 저장소에 백업하는 패턴을 적용하세요
    - 예시: state["external_snapshot"] = {"order_id": order_id, "payment_status": status}

    LangGraph Human Interrupt 필수 요소:
    1. interrupt() 함수로 Pause
    2. Command(resume=...) 로 Resume
    3. checkpointer로 상태 저장 (compile 시 설정됨)
    4. thread_id로 세션 관리
    5. interrupt 전에는 side effect 없음 (비효과적 코드만)

    Payload Schema (표준화):
    ```json
    {
        "type": "option_selector",
        "question": "추가 정보가 필요합니다.",
        "options": [{"title": "...", "description": "..."}],
        "node_ref": "option_pause",
        "event_id": "evt_abc123",
        "timestamp": "2024-01-01T12:00:00",
        "data": {"user_input": "..."}
    }
    ```
    """
    
    # =========================================================================
    # [BEFORE INTERRUPT] 비효과적 코드만 (side effect 없음)
    # =========================================================================
    # 1. 인터럽트 페이로드 생성 (순수 함수, 외부 호출 없음)
    # [UPDATE] Interrupt Payload 생성 (Semantic Key 적용)
    # 기존 코드: payload = create_option_interrupt(state)
    # Refactoring: interrupt_id 명시
    interrupt_id = "analyze_direction_select"
    
    # [CRITICAL NOTICE]
    # ⚠️ DO NOT put side-effects before interrupt!
    # interrupt() 이전 구간에서는 외부 API 호출, DB 저장, LLM 생성 등이 절대 불가합니다.
    # Resume 시 이 노드는 처음부터 재실행되므로 사이드 이펙트가 중복 발생할 수 있습니다.
    
    payload = create_option_interrupt(state, interrupt_id=interrupt_id)
    
    # [NEW] Semantic Key for Safety (Resume Mismatch 방지)
    # create_option_interrupt 내부에서 이미 설정되지만, 명시적으로 확인
    if payload.get("interrupt_id") != interrupt_id:
        # Should not happen if create_option_interrupt works correctly
        payload["interrupt_id"] = interrupt_id
        
    print(f"[HITL] Option Interrupt Payload Created (ID: {interrupt_id})")
    payload["event_id"] = f"evt_{uuid.uuid4().hex[:12]}"
    payload["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    
    # [NOTE] "Pause 직전 상태 백업" 피드백 관련:
    # LangGraph에서 node 실행 중 interrupt()가 호출되면 실행이 중단되므로,
    # interrupt() 호출 이전에 state를 update_state(...)로 DB에 저장할 수 없습니다.
    # (Command를 리턴해야만 저장됨).
    # 따라서 payload 데이터 자체는 LangGraph Checkpointing 메커니즘에 의해 저장되며,
    # Resume 시에는 이 payload를 기반으로 복원됩니다.
    # 별도의 'last_interrupt' State 백업은 Resume 후 handle_user_response에서 수행하거나,
    # 이전 노드(Analyzer)에서 수행해야 합니다. 현재 구조에서는 Checkpoint를 신뢰합니다.
    
    # =========================================================================
    # [INTERRUPT] 실행 중단 - 사용자 응답 대기 (무한 루프로 검증)
    # =========================================================================
    user_response = None
    
    # [NEW] Input Validation Loop - Code Reviewer's Advice
    MAX_RETRIES = settings.HITL_MAX_RETRIES
    retry_count = 0
    
    # [CRITICAL WARNING for Maintainers]
    # interrupt() 호출 이전에는 절대 LLM 호출, DB 저장 등 Side Effect가 있는 코드를 배치하지 마십시오.
    # 재개(Resume) 시 이 노드는 처음부터 다시 실행되므로, Side Effect가 중복 실행(Duplicate Execution)될 수 있습니다.
    # (LangGraph Best Practice: Side Effect는 항상 interrupt 이후 혹은 별도 노드에서 처리)

    # =========================================================================
    # ⚠️ CRITICAL: Multi-Interrupt Chain 주의사항
    # =========================================================================
    # interrupt() 호출 순서/갯수는 절대 변경되지 않아야 합니다.
    # Resume matching이 index 기반이므로, Pause 구조를 동적으로 변경하면 안 됩니다.
    #
    # 예시 (잘못된 패턴):
    #   if condition:
    #       interrupt(payload1)  # index 0
    #   else:
    #       interrupt(payload2)  # 조건에 따라 index가 달라짐 → Resume Mismatch!
    #
    # 예시 (올바른 패턴 - 현재 구현):
    #   while retry_count < MAX_RETRIES:
    #       interrupt(payload)   # 항상 동일한 위치에서 호출 → 안전
    # =========================================================================

    # [NEW] Input Validation Loop with Safety Limit
    while retry_count < MAX_RETRIES:
        # [NEW] 재시도 시 사용자에게 에러 피드백 제공
        if retry_count > 0:
            payload["error"] = "⚠️ 입력값이 비어있습니다. 다시 선택해주세요."
            # [OPTION] 질문 업데이트 (선택 사항)
            # payload["question"] = f"[재입력 요청] {payload['question']}"
            
        # interrupt() 호출 시 실행 중단 -> Resume 시 값 반환
        user_response = interrupt(payload)
        
        # 유효성 검사: 값이 존재해야 함 (None, 빈 문자열 등 방지)
        if user_response:
            # [LOG] 사용자 응답 기록
            get_file_logger().info(f"[HITL] User Response: {user_response}")
            print(f"[Human-Node] Valid Input Received: {user_response}")
            break
            
        retry_count += 1
        print(f"[Human-Node] Invalid Input (Empty). Retry {retry_count}/{MAX_RETRIES}")
        
    # 최대 재시도 초과 시 안전 조치
    if not user_response:
        msg = f"[HITL] Max retries reached ({MAX_RETRIES}). Forcing default action (continue)."
        print(msg)
        get_file_logger().warning(msg)
        user_response = {"action": "continue", "value": "default_fallback"}

    
    
    # =========================================================================
    # [AFTER INTERRUPT] Resume 후 실행되는 코드
    # =========================================================================
    # user_response는 Resume 시 Command(resume=...)로 전달된 값

    # [NEW] last_interrupt 백업 (Resume 전에 저장 - handle_user_response에서 참조용)
    state_with_interrupt = update_state(state, last_interrupt=payload)

    # 3. 사용자 응답으로 상태 업데이트 (last_interrupt 정보 포함)
    updated_state = handle_user_response(state_with_interrupt, user_response)

    # [NEW] 재시도 초과로 인한 강제 진행인 경우 UI 알림(Error) 추가
    if isinstance(user_response, dict) and user_response.get("value") == "default_fallback":
        # 기존 에러가 있다면 덮어쓰지 않도록 주의 (또는 이어붙이기)
        base_err = updated_state.get("error", "")
        fallback_msg = "⚠️ 입력 횟수 초과: 기본 설정으로 자동 진행합니다."
        updated_state["error"] = f"{base_err}\n{fallback_msg}" if base_err else fallback_msg

    # [NEW] Multiple Interrupt Check (연쇄 질문 패턴)
    # "직접 입력" 또는 "기타" 옵션 선택 시 -> 추가 정보 입력 폼으로 전환 (재귀 호출)
    selected_opt = user_response.get("selected_option")
    if selected_opt and isinstance(selected_opt, dict):
        title = selected_opt.get("title", "")
        if "직접" in title or "기타" in title:
             print(f"[HITL] Detailed Input Required for option: {title}")
             # 재귀적 인터럽트를 위해 상태 업데이트
             updated_state = update_state(
                 updated_state,
                 need_more_info=True,
                 input_schema_name="free_text_input",  # 상세 입력 모드 활성화
                 option_question=f"선택하신 '{title}'에 대한 구체적인 내용을 입력해주세요.",
                 options=[], # 기존 옵션 제거 (폼 모드)
                 retry_count=0 
             )
             # 자기 자신(option_pause)으로 이동하여 다시 interrupt 발생
             return Command(update=updated_state, goto="option_pause")

    return Command(
        update=updated_state,
        goto="analyze"  # 새 정보로 다시 분석
    )
