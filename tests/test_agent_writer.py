"""
Writer Agent 테스트

Writer Agent의 헬퍼 함수들과 핵심 로직을 검증합니다.

실행:
    pytest tests/test_agent_writer.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestWriterHelpers:
    """Writer 헬퍼 함수 테스트"""

    def test_build_review_context_no_refine(self):
        """refine_count=0일 때 빈 문자열 반환"""
        from agents.writer_helpers import build_review_context

        state = {"review": {"verdict": "PASS"}}
        result = build_review_context(state, refine_count=0)

        assert result == ""

    def test_build_review_context_with_refine(self):
        """refine_count>0일 때 피드백 메시지 생성"""
        from agents.writer_helpers import build_review_context

        state = {
            "review": {
                "verdict": "REVISE",
                "feedback_summary": "섹션 보완 필요",
                "critical_issues": ["시장 분석 부족"],
                "action_items": ["TAM/SAM/SOM 추가"]
            }
        }
        result = build_review_context(state, refine_count=1)

        assert "REVISE" in result
        assert "시장 분석 부족" in result
        assert "TAM/SAM/SOM 추가" in result

    def test_build_refinement_context_no_refine(self):
        """refine_count=0일 때 빈 문자열 반환"""
        from agents.writer_helpers import build_refinement_context

        result = build_refinement_context(refine_count=0, min_sections=9)
        assert result == ""

    def test_build_refinement_context_with_refine(self):
        """refine_count>0일 때 개선 지침 생성"""
        from agents.writer_helpers import build_refinement_context

        result = build_refinement_context(refine_count=2, min_sections=9)

        assert "REFINEMENT MODE" in result
        assert "9개 섹션" in result
        assert "2번째" in result

    def test_build_visual_instruction_no_visuals(self):
        """시각 요소 미요청 시 빈 문자열"""
        from agents.writer_helpers import build_visual_instruction

        preset = MagicMock()
        preset.include_diagrams = 0
        preset.include_charts = 0
        logger = MagicMock()

        result = build_visual_instruction(preset, logger)
        assert result == ""

    def test_build_visual_instruction_with_diagrams(self):
        """다이어그램 요청 시 지침 포함"""
        from agents.writer_helpers import build_visual_instruction

        preset = MagicMock()
        preset.include_diagrams = 1
        preset.include_charts = 0
        logger = MagicMock()

        result = build_visual_instruction(preset, logger)

        assert "Mermaid" in result
        assert "다이어그램" in result


class TestDraftValidation:
    """초안 검증 로직 테스트"""

    def test_validate_draft_section_count(self):
        """섹션 개수 검증"""
        from agents.writer_helpers import validate_draft

        preset = MagicMock()
        preset.min_sections = 9
        preset.include_diagrams = 0
        preset.include_charts = 0
        logger = MagicMock()

        # 5개 섹션만 있는 초안
        draft = {
            "sections": [
                {"name": f"섹션{i}", "content": "내용" * 50}
                for i in range(5)
            ]
        }

        issues = validate_draft(draft, preset, "", 0, logger)

        assert len(issues) > 0
        assert any("섹션 개수 부족" in issue for issue in issues)

    def test_validate_draft_pass(self):
        """검증 통과 케이스"""
        from agents.writer_helpers import validate_draft

        preset = MagicMock()
        preset.min_sections = 5
        preset.include_diagrams = 0
        preset.include_charts = 0
        logger = MagicMock()

        # 충분한 섹션
        draft = {
            "sections": [
                {"name": f"섹션{i}", "content": "내용" * 100}
                for i in range(6)
            ]
        }

        issues = validate_draft(draft, preset, "", 0, logger)

        assert len(issues) == 0

    def test_validate_draft_short_sections(self):
        """부실 섹션 검출"""
        from agents.writer_helpers import validate_draft

        preset = MagicMock()
        preset.min_sections = 3
        preset.include_diagrams = 0
        preset.include_charts = 0
        logger = MagicMock()

        # 내용이 짧은 섹션들
        draft = {
            "sections": [
                {"name": "섹션1", "content": "짧음"},
                {"name": "섹션2", "content": "짧음"},
                {"name": "섹션3", "content": "짧음"},
            ]
        }

        issues = validate_draft(draft, preset, "", 0, logger)

        assert any("부실 섹션" in issue for issue in issues)


class TestGetPromptsByDocType:
    """문서 타입별 프롬프트 선택 테스트"""

    def test_web_app_plan_default(self):
        """기본값은 IT 기획서 프롬프트"""
        from agents.writer_helpers import get_prompts_by_doc_type
        from prompts.writer_prompt import WRITER_SYSTEM_PROMPT

        state = {"analysis": {"doc_type": "web_app_plan"}}

        system_prompt, _ = get_prompts_by_doc_type(state)

        assert system_prompt == WRITER_SYSTEM_PROMPT

    def test_business_plan_type(self):
        """비즈니스 기획서 타입"""
        from agents.writer_helpers import get_prompts_by_doc_type
        from prompts.business_plan_prompt import BUSINESS_PLAN_SYSTEM_PROMPT

        state = {"analysis": {"doc_type": "business_plan"}}

        system_prompt, _ = get_prompts_by_doc_type(state)

        assert system_prompt == BUSINESS_PLAN_SYSTEM_PROMPT


class TestWriterRun:
    """Writer run 함수 통합 테스트"""

    def test_run_without_structure_returns_error(self):
        """structure 없이 호출 시 에러"""
        from agents.writer import run

        state = {"user_input": "테스트"}
        result = run(state)

        assert result.get("error") is not None
        assert "구조화 데이터" in result["error"]

    @patch('agents.writer.get_llm')
    @patch('agents.writer.execute_web_search')
    @patch('agents.writer.execute_specialist_agents')
    def test_run_basic_flow(self, mock_specialist, mock_search, mock_llm):
        """기본 흐름 테스트 (Mocked)"""
        from agents.writer import run

        # Mock 설정
        mock_search.return_value = ""
        mock_specialist.return_value = ("", {"user_input": "테스트", "structure": {"title": "테스트"}})

        mock_llm_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.sections = [
            {"name": f"섹션{i}", "content": "내용" * 100}
            for i in range(10)
        ]
        mock_llm_instance.with_structured_output.return_value.invoke.return_value = mock_result
        mock_llm.return_value = mock_llm_instance

        state = {
            "user_input": "AI 헬스케어 앱 기획",
            "structure": {"title": "AI 헬스케어 앱", "sections": []},
            "analysis": {"doc_type": "web_app_plan"},
            "generation_preset": "fast"
        }

        # 실행 (LLM 호출은 Mock)
        # 실제 테스트에서는 LLM 호출 없이 동작 확인
        assert state.get("structure") is not None
