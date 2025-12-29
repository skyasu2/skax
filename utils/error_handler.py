"""
Error Handler Utility

노드 실행 중 발생하는 예외를 일관되게 처리하기 위한 데코레이터 및 유틸리티를 제공합니다.
모든 노드 함수에 이 데코레이터를 적용하여 코드 중복을 줄이고 에러 추적성을 높입니다.

에러 카테고리:
- LLM_ERROR: LLM API 호출 실패 (타임아웃, 토큰 초과 등)
- NETWORK_ERROR: 네트워크 관련 오류 (웹 검색, MCP 등)
- VALIDATION_ERROR: 입력/출력 검증 실패
- STATE_ERROR: 상태 관리 오류
- UNKNOWN_ERROR: 분류되지 않은 오류
"""

import functools
import traceback
from datetime import datetime
from typing import Callable, Any, Literal
from graph.state import PlanCraftState

# =============================================================================
# 커스텀 예외 클래스
# =============================================================================

class PlanCraftError(Exception):
    """PlanCraft 기본 예외 클래스"""
    category: str = "UNKNOWN_ERROR"
    
    def __init__(self, message: str, details: str = None):
        super().__init__(message)
        self.message = message
        self.details = details


class LLMError(PlanCraftError):
    """LLM API 관련 오류 (타임아웃, 토큰 초과, API 오류 등)"""
    category = "LLM_ERROR"


class NetworkError(PlanCraftError):
    """네트워크 관련 오류 (웹 검색, MCP, URL 조회 등)"""
    category = "NETWORK_ERROR"


class ValidationError(PlanCraftError):
    """입력/출력 데이터 검증 오류"""
    category = "VALIDATION_ERROR"


class StateError(PlanCraftError):
    """상태 관리 관련 오류"""
    category = "STATE_ERROR"


# =============================================================================
# 에러 카테고리 분류 함수
# =============================================================================

def categorize_error(exception: Exception) -> str:
    """
    예외 유형을 분석하여 에러 카테고리를 반환합니다.
    
    Returns:
        str: 에러 카테고리 (LLM_ERROR, NETWORK_ERROR, VALIDATION_ERROR, STATE_ERROR, UNKNOWN_ERROR)
    """
    error_msg = str(exception).lower()
    error_type = type(exception).__name__
    
    # PlanCraft 커스텀 예외
    if isinstance(exception, PlanCraftError):
        return exception.category
    
    # LLM 관련 오류
    llm_keywords = ["openai", "azure", "api", "token", "rate limit", "timeout", "model", "completion"]
    if any(kw in error_msg for kw in llm_keywords) or "openai" in error_type.lower():
        return "LLM_ERROR"
    
    # 네트워크 관련 오류
    network_keywords = ["connection", "network", "http", "url", "request", "socket", "dns", "ssl"]
    network_types = ["ConnectionError", "TimeoutError", "HTTPError", "URLError", "SSLError"]
    if any(kw in error_msg for kw in network_keywords) or error_type in network_types:
        return "NETWORK_ERROR"
    
    # 검증 관련 오류
    validation_types = ["ValidationError", "ValueError", "TypeError", "KeyError", "AttributeError"]
    if error_type in validation_types or "validation" in error_msg:
        return "VALIDATION_ERROR"
    
    # 상태 관련 오류
    if "state" in error_msg or "typeddict" in error_msg:
        return "STATE_ERROR"
    
    return "UNKNOWN_ERROR"


# =============================================================================
# 에러 핸들링 데코레이터
# =============================================================================

def handle_node_error(func: Callable) -> Callable:
    """
    [Decorator] 노드 함수 실행 중 예외 발생 시 에러 상태를 업데이트합니다.
    
    기능:
    1. 예외가 발생하면 에러 메시지와 트레이스백을 추출합니다.
    2. 에러를 카테고리별로 분류하여 디버깅을 용이하게 합니다.
    3. State 객체의 'error', 'error_category', 'step_status' 필드를 업데이트합니다.
    4. Graph 실행이 중단되지 않고 FAILED 상태로 다음 단계(또는 UI)로 넘어가도록 합니다.
    """
    @functools.wraps(func)
    def wrapper(state: PlanCraftState, *args, **kwargs) -> PlanCraftState:
        from utils.file_logger import get_file_logger
        logger = get_file_logger()
        
        try:
            return func(state, *args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            error_category = categorize_error(e)
            tb = traceback.format_exc()
            
            # 카테고리별 로깅
            logger.error(f"[{error_category}] Node '{func.__name__}' Failed: {error_msg}")
            logger.debug(f"Traceback:\n{tb}")
            
            # 실패 이력 생성 - TypedDict dict 접근
            current_history = state.get("step_history", []) or []
            fail_record = {
                "step": func.__name__,
                "status": "FAILED",
                "summary": f"[{error_category}] {error_msg[:50]}...",
                "error": error_msg,
                "error_category": error_category,
                "timestamp": datetime.now().isoformat()
            }
            
            # TypedDict State 업데이트
            from graph.state import update_state
            
            return update_state(
                state,
                error=error_msg,
                error_message=f"[{error_category}] {error_msg}",
                error_category=error_category,
                step_status="FAILED",
                last_error=error_msg,
                step_history=current_history + [fail_record]
            )
            
    return wrapper

