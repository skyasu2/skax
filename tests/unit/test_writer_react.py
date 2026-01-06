"""
Writer ReAct 패턴 테스트

Writer가 작성 중 자율적으로 도구를 호출하는 ReAct 패턴 테스트입니다.

실행:
    pytest tests/unit/test_writer_react.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError


# =============================================================================
# Writer Tools Tests
# =============================================================================

class TestWriterTools:
    """Writer 도구 정의 테스트"""

    def test_tools_import(self):
        """도구 임포트 테스트"""
        from tools.writer_tools import (
            get_writer_tools,
            request_specialist_analysis,
            search_rag_documents,
            search_web,
        )

        tools = get_writer_tools()
        assert len(tools) == 3
        # Tool 객체는 .invoke() 메서드를 가짐
        assert hasattr(request_specialist_analysis, 'invoke')
        assert hasattr(search_rag_documents, 'invoke')
        assert hasattr(search_web, 'invoke')

    def test_tool_names(self):
        """도구 이름 테스트"""
        from tools.writer_tools import get_writer_tools

        tools = get_writer_tools()
        tool_names = [tool.name for tool in tools]

        assert "request_specialist_analysis" in tool_names
        assert "search_rag_documents" in tool_names
        assert "search_web" in tool_names

    def test_request_specialist_analysis_schema(self):
        """Specialist 분석 요청 스키마 테스트"""
        from tools.writer_tools import SpecialistQueryInput

        # 유효한 입력
        valid_input = SpecialistQueryInput(
            specialist_type="market",
            query="TAM/SAM/SOM 분석",
            context="피트니스 앱"
        )
        assert valid_input.specialist_type == "market"
        assert "TAM" in valid_input.query

        # specialist_type 유효성 검사 (Literal 타입)
        with pytest.raises(ValidationError):
            SpecialistQueryInput(
                specialist_type="invalid_type",  # 유효하지 않은 타입
                query="테스트"
            )

    def test_rag_search_schema(self):
        """RAG 검색 스키마 테스트"""
        from tools.writer_tools import RAGSearchInput

        valid_input = RAGSearchInput(query="비즈니스 모델 가이드")
        assert "비즈니스" in valid_input.query

    def test_web_search_schema(self):
        """웹 검색 스키마 테스트"""
        from tools.writer_tools import WebSearchInput

        valid_input = WebSearchInput(query="2024 피트니스 앱 시장")
        assert "피트니스" in valid_input.query

    @patch('tools.search_client.get_search_client')
    def test_search_web_success(self, mock_get_client):
        """웹 검색 성공 테스트"""
        from tools.writer_tools import search_web

        mock_client = Mock()
        mock_client.search.return_value = "2024년 피트니스 앱 시장 규모: 5조원..."
        mock_get_client.return_value = mock_client

        result = search_web.invoke({
            "query": "2024 피트니스 앱 시장 규모"
        })

        assert "피트니스" in result or "시장" in result


# =============================================================================
# Writer ReAct Mode Tests
# =============================================================================

class TestWriterReactMode:
    """Writer ReAct 모드 활성화 테스트"""

    def test_react_enabled_for_balanced_preset(self):
        """Balanced 프리셋에서 ReAct 활성화 확인"""
        from utils.settings import get_preset

        preset = get_preset("balanced")
        assert preset.enable_writer_react is True
        assert preset.react_max_tool_calls == 3

    def test_react_enabled_for_quality_preset(self):
        """Quality 프리셋에서 ReAct 활성화 확인"""
        from utils.settings import get_preset

        preset = get_preset("quality")
        assert preset.enable_writer_react is True
        assert preset.react_max_tool_calls == 3

    def test_react_disabled_for_fast_preset(self):
        """Fast 프리셋에서 ReAct 비활성화 확인"""
        from utils.settings import get_preset

        preset = get_preset("fast")
        assert preset.enable_writer_react is False


# =============================================================================
# Writer ReAct Prompt Tests
# =============================================================================

class TestWriterReactPrompt:
    """Writer ReAct 프롬프트 테스트"""

    def test_react_instruction_exists(self):
        """ReAct 지침 존재 확인"""
        from prompts.writer_prompt import WRITER_REACT_INSTRUCTION

        assert "도구 활용 지침" in WRITER_REACT_INSTRUCTION
        assert "ReAct" in WRITER_REACT_INSTRUCTION

    def test_react_instruction_contains_tools(self):
        """ReAct 지침에 도구 설명 포함 확인"""
        from prompts.writer_prompt import WRITER_REACT_INSTRUCTION

        assert "request_specialist_analysis" in WRITER_REACT_INSTRUCTION
        assert "search_rag_documents" in WRITER_REACT_INSTRUCTION
        assert "search_web" in WRITER_REACT_INSTRUCTION

    def test_react_instruction_contains_limits(self):
        """ReAct 지침에 제한 사항 포함 확인"""
        from prompts.writer_prompt import WRITER_REACT_INSTRUCTION

        assert "최대 3회" in WRITER_REACT_INSTRUCTION
        assert "신중하게" in WRITER_REACT_INSTRUCTION


# =============================================================================
# Workflow Integration Tests
# =============================================================================

class TestWorkflowIntegration:
    """Workflow 통합 테스트"""

    def test_workflow_structure_to_write_direct(self):
        """structure → write 직접 연결 확인"""
        # workflow 생성 시 data_gap_analysis 노드 없이 동작하는지 확인
        # 실제 workflow 생성은 무거우므로 import만 테스트
        from graph.workflow import create_workflow

        # create_workflow가 오류 없이 호출되는지 확인
        # (실제 생성은 시간이 오래 걸릴 수 있음)
        assert callable(create_workflow)

    def test_dynamic_qa_deprecated(self):
        """Dynamic Q&A 모듈 deprecated 확인"""
        from graph.nodes.dynamic_qa import __doc__ as module_doc

        assert "DEPRECATED" in module_doc
        assert "Writer ReAct" in module_doc


# =============================================================================
# ReAct Loop Integration Tests (Mock)
# =============================================================================

class TestReactLoopIntegration:
    """ReAct 루프 통합 테스트 (Mock 기반)"""

    def test_react_loop_function_exists(self):
        """ReAct 루프 함수 존재 확인"""
        from agents.writer import _run_with_react_loop, _execute_react_tool

        assert callable(_run_with_react_loop)
        assert callable(_execute_react_tool)

    def test_react_constants_defined(self):
        """ReAct 상수 정의 확인"""
        from agents.writer import REACT_MAX_TOOL_CALLS, REACT_MAX_ITERATIONS

        assert REACT_MAX_TOOL_CALLS == 3
        assert REACT_MAX_ITERATIONS == 5

    def test_execute_react_tool_unknown(self):
        """알 수 없는 도구 실행 테스트"""
        from agents.writer import _execute_react_tool

        logger = Mock()
        result = _execute_react_tool("unknown_tool", {}, {}, logger)

        assert "[ERROR]" in result
        assert "알 수 없는 도구" in result

    def test_execute_react_tool_success(self):
        """도구 실행 성공 테스트"""
        from agents.writer import _execute_react_tool

        mock_tool = Mock()
        mock_tool.invoke.return_value = "도구 실행 결과"

        tool_map = {"test_tool": mock_tool}
        logger = Mock()

        result = _execute_react_tool("test_tool", {"arg": "value"}, tool_map, logger)

        assert result == "도구 실행 결과"
        mock_tool.invoke.assert_called_once_with({"arg": "value"})

    def test_execute_react_tool_failure(self):
        """도구 실행 실패 테스트"""
        from agents.writer import _execute_react_tool

        mock_tool = Mock()
        mock_tool.invoke.side_effect = Exception("도구 오류")

        tool_map = {"failing_tool": mock_tool}
        logger = Mock()

        result = _execute_react_tool("failing_tool", {}, tool_map, logger)

        assert "[ERROR]" in result
        assert "실행 실패" in result
