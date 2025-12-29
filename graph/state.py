"""
PlanCraft Agent - 상태 정의 모듈 (TypedDict 기반)

LangGraph 최신 Best Practice에 따라 Input/Output/Internal State를 명확히 분리합니다.
- API/UI는 PlanCraftInput/Output만 노출
- 내부 로직은 PlanCraftState(전체) 사용
- 문서화, 테스트, 자동화 이점 극대화
"""

from typing import Optional, List, Dict, Any, Literal, Annotated
from typing_extensions import TypedDict, NotRequired

# 참고: LangGraph RemainingSteps는 버전 호환성 이슈로 사용하지 않음
# 대신 refine_count + MAX_REFINE_LOOPS로 무한 루프 방지

# =============================================================================
# Constants: 안전 실행 한계
# =============================================================================
MAX_REFINE_LOOPS = 3          # 최대 개선 루프 횟수
MIN_REMAINING_STEPS = 5       # 최소 남은 스텝 (안전 탈출 기준)

# =============================================================================
# Input Schema (External API/UI Interface)
# =============================================================================

class PlanCraftInput(TypedDict, total=False):
    """
    외부에서 유입되는 입력 데이터 스키마
    
    API/UI/테스트에서만 사용하며, 최소한의 필수 입력만 정의합니다.
    """
    user_input: str  # Required
    file_content: Optional[str]
    refine_count: int
    retry_count: int
    previous_plan: Optional[str]
    thread_id: str


# =============================================================================
# Output Schema (External API/UI Interface)
# =============================================================================

class PlanCraftOutput(TypedDict, total=False):
    """
    최종적으로 반환되는 출력 데이터 스키마

    API 응답, UI 렌더링, 테스트 검증에 사용됩니다.
    """
    final_output: Optional[str]
    step_history: List[dict]
    chat_history: List[dict]
    error: Optional[str]
    error_message: Optional[str]
    retry_count: int
    chat_summary: Optional[str]

    # AI 분석 데이터 (UI에서 설계도 표시용)
    analysis: Optional[dict]
    structure: Optional[dict]
    review: Optional[dict]
    draft: Optional[dict]
    
    # [FIX] 인터럽트/추가질문 관련 필드 (UI 렌더링용)
    options: Optional[List[dict]]
    option_question: Optional[str]
    need_more_info: bool


# =============================================================================
# Interrupt Payload Schema (Human-in-the-loop Interface)
# =============================================================================

class InterruptOption(TypedDict):
    """인터럽트 선택지 스키마"""
    title: str
    description: str


class InterruptPayload(TypedDict):
    """휴먼 인터럽트 페이로드 스키마"""
    type: str  # "option", "form", "confirm"
    question: str
    options: List[InterruptOption]
    input_schema_name: Optional[str]
    data: Optional[dict]


# =============================================================================
# Internal State (Combines Input + Output + Internal Fields)
# =============================================================================

class PlanCraftState(TypedDict, total=False):
    """
    PlanCraft Agent 전체 내부 상태
    
    PlanCraftInput + PlanCraftOutput + 내부 처리용 필드를 모두 포함합니다.
    노드 함수들은 이 타입을 사용하되, 외부 인터페이스는 Input/Output만 노출합니다.
    
    ✅ Best Practice:
    - 외부 API/UI: PlanCraftInput/Output 사용
    - 내부 Agent/Node: PlanCraftState 사용
    - 문서화: Input/Output의 .json_schema() 활용
    """
    
    # ========== From PlanCraftInput ==========
    user_input: str
    file_content: Optional[str]
    refine_count: int
    retry_count: int
    previous_plan: Optional[str]
    thread_id: str
    
    # ========== From PlanCraftOutput ==========
    final_output: Optional[str]
    step_history: List[dict]
    chat_history: List[dict]
    error: Optional[str]
    error_message: Optional[str]
    chat_summary: Optional[str]
    
    # ========== Internal Fields (Not exposed to API/UI) ==========
    
    # Context
    rag_context: Optional[str]
    web_context: Optional[str]
    web_urls: Optional[List[str]]
    
    # Analysis (stored as dict to avoid Pydantic dependency)
    analysis: Optional[dict]
    input_schema_name: Optional[str]
    need_more_info: bool
    options: List[dict]
    option_question: Optional[str]
    selected_option: Optional[str]
    messages: List[Dict[str, str]]
    
    # Structure
    structure: Optional[dict]
    
    # Draft
    draft: Optional[dict]
    
    # Review & Refine
    review: Optional[dict]
    refined: bool
    restart_count: int  # [NEW] Analyzer 복귀 횟수 (동적 라우팅)
    
    # Metadata & Operations
    current_step: str
    step_status: Literal["RUNNING", "SUCCESS", "FAILED"]
    last_error: Optional[str]
    execution_time: Optional[str]

    # ========== Graceful End-of-Loop (LangGraph Best Practice) ==========
    # 무한 루프 방지를 위한 남은 스텝 카운터
    # 주의: Annotated[int, RemainingSteps] 대신 단순 int 사용 (버전 호환성)
    # 실제 카운터는 workflow.py의 should_refine_again()에서 refine_count로 관리
    remaining_steps: int

    # Interrupt & Routing (Human-in-the-loop)
    confirmed: Optional[bool]
    uploaded_content: Optional[str]
    routing_decision: Optional[str]


# =============================================================================
# Helper Functions (Replacing Pydantic methods)
# =============================================================================

def create_initial_state(
    user_input: str,
    file_content: str = None,
    previous_plan: str = None,
    thread_id: str = "default_thread"
) -> PlanCraftState:
    """
    초기 상태를 생성합니다.
    
    TypedDict 기반으로 변경되어 Pydantic 의존성이 없습니다.
    """
    from datetime import datetime
    
    return {
        # Input fields
        "user_input": user_input,
        "file_content": file_content,
        "refine_count": 0,
        "retry_count": 0,
        "previous_plan": previous_plan,
        "thread_id": thread_id,
        
        # Output fields
        "final_output": None,
        "step_history": [],
        "chat_history": [],
        "error": None,
        "error_message": None,
        "chat_summary": None,
        
        # Internal fields
        "rag_context": None,
        "web_context": None,
        "web_urls": None,
        "analysis": None,
        "input_schema_name": None,
        "need_more_info": False,
        "options": [],
        "option_question": None,
        "selected_option": None,
        "messages": [{"role": "user", "content": user_input}],
        "structure": None,
        "draft": None,
        "review": None,
        "refined": False,
        "current_step": "start",
        "step_status": "RUNNING",
        "last_error": None,
        "execution_time": datetime.now().isoformat(),

        # Interrupt & Routing
        "confirmed": None,
        "uploaded_content": None,
        "routing_decision": None
    }


def update_state(base_state: PlanCraftState, **updates) -> PlanCraftState:
    """
    State 업데이트 헬퍼 (Pydantic의 model_copy 대체)

    새로운 dict를 반환하여 불변성을 보장합니다.

    Usage:
        new_state = update_state(state, current_step="analyze", error=None)
    """
    return {**base_state, **updates}


def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    dict 또는 Pydantic 객체에서 안전하게 값을 추출합니다.

    LangGraph 내부에서 state가 dict 또는 Pydantic 객체로
    전달될 수 있으므로, 양쪽 모두 지원합니다.

    Args:
        obj: dict 또는 Pydantic 객체
        key: 추출할 키/속성명
        default: 기본값 (기본: None)

    Returns:
        추출된 값 또는 기본값

    Usage:
        topic = safe_get(analysis, "topic", "")
        sections = safe_get(structure, "sections", [])
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def validate_state(state: Any) -> bool:
    """
    State가 dict 형태인지 검증합니다.

    디버깅 및 런타임 방어용으로 사용합니다.

    Args:
        state: 검증할 상태 객체

    Returns:
        bool: dict 형태이면 True

    Raises:
        TypeError: dict가 아닌 경우 (선택적으로 사용)

    Usage:
        assert validate_state(state), f"Expected dict, got {type(state)}"
    """
    return isinstance(state, dict) and hasattr(state, "get")
