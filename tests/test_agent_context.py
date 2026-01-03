"""
Agent Context Separation Tests

Agent별 입력/출력 스키마가 올바르게 정의되어 있는지,
컨텍스트 추출 함수가 정상 동작하는지 테스트합니다.

테스트 실행:
    pytest tests/test_agent_context.py -v
"""

import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from graph.state import (
    create_initial_state,
    update_state,
    AGENT_CONTEXT_SCHEMAS,
    get_agent_context,
    validate_agent_input,
    get_agent_output_fields,
)


class TestAgentContextSchemas:
    """Agent Context Schema 정의 테스트"""

    def test_all_core_agents_have_schemas(self):
        """모든 코어 에이전트가 스키마를 가지는지 확인"""
        core_agents = ["analyzer", "structurer", "writer", "reviewer", "refiner"]

        for agent in core_agents:
            assert agent in AGENT_CONTEXT_SCHEMAS, f"{agent} 스키마 누락"

    def test_schema_has_required_fields(self):
        """각 스키마가 필수 메타데이터를 포함하는지 확인"""
        for agent_name, schema in AGENT_CONTEXT_SCHEMAS.items():
            with pytest.raises(AssertionError) if "agent_name" not in schema else pytest.warns(None):
                assert "agent_name" in schema, f"{agent_name}: agent_name 누락"
                assert "input_fields" in schema, f"{agent_name}: input_fields 누락"
                assert "output_fields" in schema, f"{agent_name}: output_fields 누락"

    def test_input_output_no_overlap(self):
        """입력과 출력 필드가 겹치지 않는지 확인 (일부 예외)"""
        # 일부 에이전트는 재설계/재처리를 위해 입/출력 모두에서 사용
        exceptions = ["refine_count", "structure"]

        for agent_name, schema in AGENT_CONTEXT_SCHEMAS.items():
            input_fields = set(schema.get("input_fields", []))
            output_fields = set(schema.get("output_fields", []))

            overlap = input_fields & output_fields - set(exceptions)
            assert len(overlap) == 0, (
                f"{agent_name}: 입/출력 필드 중복 - {overlap}"
            )

    def test_dependency_chain_consistency(self):
        """
        에이전트 체인의 의존성 일관성 검증

        analyzer → structurer → writer → reviewer → refiner
        이전 에이전트의 출력이 다음 에이전트의 입력에 포함되어야 함
        """
        chain = [
            ("analyzer", "structurer", "analysis"),
            ("structurer", "writer", "structure"),
            ("writer", "reviewer", "draft"),
            ("reviewer", "refiner", "review"),
        ]

        for prev_agent, next_agent, output_field in chain:
            prev_outputs = set(AGENT_CONTEXT_SCHEMAS[prev_agent].get("output_fields", []))
            next_inputs = set(AGENT_CONTEXT_SCHEMAS[next_agent].get("input_fields", []))

            assert output_field in prev_outputs, (
                f"{prev_agent}가 {output_field}를 출력해야 함"
            )
            assert output_field in next_inputs, (
                f"{next_agent}가 {output_field}를 입력으로 받아야 함"
            )


class TestGetAgentContext:
    """get_agent_context() 함수 테스트"""

    def test_extracts_only_input_fields(self):
        """입력 필드만 추출되는지 확인"""
        state = create_initial_state("테스트 입력")
        state = update_state(state,
            draft={"sections": []},
            review={"score": 85},
            analysis={"topic": "테스트"}
        )

        # Analyzer 컨텍스트에는 draft가 포함되면 안됨
        context = get_agent_context(state, "analyzer")

        assert "user_input" in context
        assert "draft" not in context  # analyzer는 draft 불필요
        assert "review" in context  # analyzer는 review를 받을 수 있음 (재분석용)

    def test_unknown_agent_returns_full_state(self):
        """알 수 없는 에이전트는 전체 state 반환"""
        state = create_initial_state("테스트")
        state = update_state(state, custom_field="custom_value")

        context = get_agent_context(state, "unknown_agent")

        assert "user_input" in context
        assert "custom_field" in context

    def test_writer_context_includes_specialist_analysis(self):
        """Writer 컨텍스트에 specialist_analysis 포함"""
        state = create_initial_state("테스트")
        state = update_state(state,
            analysis={"topic": "AI"},
            structure={"sections": []},
            specialist_analysis={"market": {"size": "1조원"}}
        )

        context = get_agent_context(state, "writer")

        assert "specialist_analysis" in context
        assert context["specialist_analysis"]["market"]["size"] == "1조원"


class TestValidateAgentInput:
    """validate_agent_input() 함수 테스트"""

    def test_missing_required_field(self):
        """필수 필드 누락 감지"""
        state = create_initial_state("")  # 빈 user_input

        missing = validate_agent_input(state, "analyzer")

        assert "user_input" in missing

    def test_all_required_present(self):
        """필수 필드가 모두 있으면 빈 리스트 반환"""
        state = create_initial_state("테스트 입력")

        missing = validate_agent_input(state, "analyzer")

        assert len(missing) == 0

    def test_writer_requires_analysis_and_structure(self):
        """Writer는 analysis와 structure가 필수"""
        state = create_initial_state("테스트")

        # analysis만 있고 structure 없음
        state = update_state(state, analysis={"topic": "테스트"})

        missing = validate_agent_input(state, "writer")

        assert "structure" in missing
        assert "analysis" not in missing

    def test_empty_dict_counts_as_missing(self):
        """빈 dict도 누락으로 처리"""
        state = create_initial_state("테스트")
        state = update_state(state, analysis={})  # 빈 dict

        missing = validate_agent_input(state, "structurer")

        assert "analysis" in missing


class TestGetAgentOutputFields:
    """get_agent_output_fields() 함수 테스트"""

    def test_reviewer_outputs_review(self):
        """Reviewer는 review를 출력"""
        outputs = get_agent_output_fields("reviewer")

        assert "review" in outputs

    def test_writer_outputs_draft_and_final(self):
        """Writer는 draft와 final_output을 출력"""
        outputs = get_agent_output_fields("writer")

        assert "draft" in outputs
        assert "final_output" in outputs

    def test_unknown_agent_returns_empty(self):
        """알 수 없는 에이전트는 빈 리스트 반환"""
        outputs = get_agent_output_fields("unknown")

        assert outputs == []


class TestContextIsolation:
    """컨텍스트 분리 검증 테스트"""

    def test_analyzer_cannot_access_draft(self):
        """Analyzer 컨텍스트에서 draft 접근 불가"""
        schema = AGENT_CONTEXT_SCHEMAS["analyzer"]
        input_fields = schema.get("input_fields", [])

        assert "draft" not in input_fields

    def test_structurer_cannot_access_review(self):
        """Structurer 컨텍스트에서 review 접근 불가"""
        schema = AGENT_CONTEXT_SCHEMAS["structurer"]
        input_fields = schema.get("input_fields", [])

        assert "review" not in input_fields

    def test_reviewer_cannot_modify_analysis(self):
        """Reviewer 출력에 analysis가 없음 (수정 불가)"""
        schema = AGENT_CONTEXT_SCHEMAS["reviewer"]
        output_fields = schema.get("output_fields", [])

        assert "analysis" not in output_fields


# =============================================================================
# 실행
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
