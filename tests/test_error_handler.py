"""
PlanCraft Unit Tests - Error Handler

에러 핸들링 유틸리티 함수들의 단위 테스트입니다.
"""

import pytest
from unittest.mock import MagicMock, patch
from utils.error_handler import (
    PlanCraftError,
    LLMError,
    NetworkError,
    ValidationError,
    StateError,
    categorize_error,
    handle_node_error
)
from graph.state import create_initial_state, update_state


class TestErrorCategorization:
    """에러 카테고리 분류 테스트"""
    
    def test_categorize_llm_error(self):
        """LLM 관련 에러 분류 테스트"""
        # OpenAI API rate limit 에러 - RATE_LIMIT_ERROR로 더 구체적으로 분류됨
        err = Exception("OpenAI API rate limit exceeded")
        assert categorize_error(err) == "RATE_LIMIT_ERROR"

        # Azure 에러
        err = Exception("Azure OpenAI deployment not found")
        assert categorize_error(err) == "LLM_ERROR"

        # 토큰 초과
        err = Exception("Maximum token limit exceeded")
        assert categorize_error(err) == "LLM_ERROR"
    
    def test_categorize_network_error(self):
        """네트워크 관련 에러 분류 테스트"""
        # 연결 오류
        err = ConnectionError("Failed to establish connection")
        assert categorize_error(err) == "NETWORK_ERROR"
        
        # HTTP 에러
        err = Exception("HTTP 503 Service Unavailable")
        assert categorize_error(err) == "NETWORK_ERROR"
        
        # URL 에러
        err = Exception("Invalid URL format")
        assert categorize_error(err) == "NETWORK_ERROR"
    
    def test_categorize_validation_error(self):
        """검증 에러 분류 테스트"""
        # ValueError
        err = ValueError("Invalid input value")
        assert categorize_error(err) == "VALIDATION_ERROR"
        
        # TypeError
        err = TypeError("Expected string, got int")
        assert categorize_error(err) == "VALIDATION_ERROR"
        
        # KeyError
        err = KeyError("missing_key")
        assert categorize_error(err) == "VALIDATION_ERROR"
    
    def test_categorize_state_error(self):
        """상태 관리 에러 분류 테스트"""
        err = Exception("State update failed")
        assert categorize_error(err) == "STATE_ERROR"
        
        err = Exception("TypedDict key error")
        assert categorize_error(err) == "STATE_ERROR"
    
    def test_categorize_custom_error(self):
        """커스텀 에러 분류 테스트"""
        err = LLMError("Custom LLM error")
        assert categorize_error(err) == "LLM_ERROR"
        
        err = NetworkError("Custom network error")
        assert categorize_error(err) == "NETWORK_ERROR"
    
    def test_categorize_unknown_error(self):
        """알 수 없는 에러 분류 테스트"""
        err = Exception("Some random error")
        assert categorize_error(err) == "UNKNOWN_ERROR"


class TestHandleNodeErrorDecorator:
    """에러 핸들링 데코레이터 테스트"""
    
    def test_successful_execution(self):
        """성공적인 노드 실행 테스트"""
        @handle_node_error
        def successful_node(state):
            return update_state(state, current_step="success")
        
        state = create_initial_state("test")
        result = successful_node(state)
        
        assert result.get("current_step") == "success"
        assert result.get("error") is None
    
    def test_error_handling(self):
        """에러 발생 시 상태 업데이트 테스트"""
        @handle_node_error
        def failing_node(state):
            raise ValueError("Test error")
        
        state = create_initial_state("test")
        result = failing_node(state)
        
        # 에러 상태 확인
        assert result.get("error") == "Test error"
        assert result.get("step_status") == "FAILED"
        assert result.get("error_category") == "VALIDATION_ERROR"
        assert "[VALIDATION_ERROR]" in result.get("error_message", "")
    
    def test_error_history_append(self):
        """에러 이력 추가 테스트"""
        @handle_node_error
        def failing_node(state):
            raise Exception("History test error")
        
        state = create_initial_state("test")
        result = failing_node(state)
        
        step_history = result.get("step_history", [])
        assert len(step_history) > 0
        
        last_entry = step_history[-1]
        assert last_entry.get("status") == "FAILED"
        assert "error_category" in last_entry


class TestCustomExceptions:
    """커스텀 예외 클래스 테스트"""
    
    def test_llm_error(self):
        """LLMError 예외 테스트"""
        err = LLMError("API timeout", details="Request took 30s")
        assert err.message == "API timeout"
        assert err.details == "Request took 30s"
        assert err.category == "LLM_ERROR"
    
    def test_network_error(self):
        """NetworkError 예외 테스트"""
        err = NetworkError("Connection refused")
        assert err.category == "NETWORK_ERROR"
    
    def test_validation_error(self):
        """ValidationError 예외 테스트"""
        err = ValidationError("Invalid schema")
        assert err.category == "VALIDATION_ERROR"
    
    def test_exception_inheritance(self):
        """예외 상속 구조 테스트"""
        err = LLMError("test")
        assert isinstance(err, PlanCraftError)
        assert isinstance(err, Exception)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
