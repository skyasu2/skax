"""
Multi-Agent Collaboration 테스트

1. Co-authoring Loop (LLM 기반 합의 감지)
2. Dynamic Q&A (Writer ↔ Specialist 동적 질의응답)

실행:
    pytest tests/test_multi_agent_collab.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError


# =============================================================================
# Schema Tests
# =============================================================================

class TestConsensusResultSchema:
    """ConsensusResult 스키마 테스트"""

    def test_valid_consensus_result(self):
        """정상적인 합의 결과 생성"""
        from utils.schemas import ConsensusResult

        result = ConsensusResult(
            consensus_reached=True,
            confidence=0.85,
            agreed_items=["시장 분석 보강", "BEP 계산 추가"],
            unresolved_items=[],
            reasoning="Reviewer가 Writer의 개선 계획에 동의함",
            suggested_next_action="finalize"
        )

        assert result.consensus_reached is True
        assert result.confidence == 0.85
        assert len(result.agreed_items) == 2

    def test_confidence_bounds(self):
        """신뢰도 범위 검증 (0.0 ~ 1.0)"""
        from utils.schemas import ConsensusResult

        # 유효 범위
        result = ConsensusResult(consensus_reached=False, confidence=0.5)
        assert result.confidence == 0.5

        # 범위 초과 시 ValidationError
        with pytest.raises(ValidationError):
            ConsensusResult(consensus_reached=True, confidence=1.5)

        with pytest.raises(ValidationError):
            ConsensusResult(consensus_reached=True, confidence=-0.1)


class TestDataGapSchemas:
    """Dynamic Q&A 스키마 테스트"""

    def test_data_gap_request(self):
        """데이터 갭 요청 스키마"""
        from utils.schemas import DataGapRequest

        request = DataGapRequest(
            requesting_section="시장 분석",
            target_specialist="market",
            query="2024년 국내 배달 앱 시장 규모 데이터",
            priority="high",
            context="TAM/SAM/SOM 계산에 필요"
        )

        assert request.target_specialist == "market"
        assert request.priority == "high"

    def test_data_gap_analysis(self):
        """데이터 갭 분석 결과 스키마"""
        from utils.schemas import DataGapAnalysis, DataGapRequest

        # 갭이 있는 경우
        analysis = DataGapAnalysis(
            has_gaps=True,
            gap_requests=[
                DataGapRequest(
                    requesting_section="재무 계획",
                    target_specialist="financial",
                    query="초기 개발 비용 산정"
                )
            ],
            can_proceed_with_assumptions=True,
            assumptions_if_proceed=["개발 비용 3억원 가정"]
        )

        assert analysis.has_gaps is True
        assert len(analysis.gap_requests) == 1
        assert analysis.can_proceed_with_assumptions is True

    def test_specialist_response(self):
        """Specialist 응답 스키마"""
        from utils.schemas import SpecialistResponse

        response = SpecialistResponse(
            request_id="gap_req_0",
            specialist_id="market",
            data={"market_size": "15조원", "growth_rate": "12%"},
            confidence=0.9,
            sources=["통계청", "업계 리포트"]
        )

        assert response.specialist_id == "market"
        assert response.confidence == 0.9
        assert len(response.sources) == 2


# =============================================================================
# Routing Tests
# =============================================================================

class TestDynamicQARouting:
    """Dynamic Q&A 라우팅 테스트"""

    def test_routing_no_gaps(self):
        """데이터 갭 없을 때 바로 write로 진행"""
        from graph.nodes.dynamic_qa import should_request_specialist

        state = {
            "data_gap_analysis": {"has_gaps": False},
            "pending_specialist_requests": []
        }

        result = should_request_specialist(state)
        assert result == "write"

    def test_routing_can_proceed_with_assumptions(self):
        """가정으로 진행 가능할 때 write로 진행"""
        from graph.nodes.dynamic_qa import should_request_specialist

        state = {
            "data_gap_analysis": {
                "has_gaps": True,
                "can_proceed_with_assumptions": True
            },
            "pending_specialist_requests": [{"query": "test"}]
        }

        result = should_request_specialist(state)
        assert result == "write"

    def test_routing_request_specialist(self):
        """데이터 갭이 있고 진행 불가능할 때 specialist 요청"""
        from graph.nodes.dynamic_qa import should_request_specialist

        state = {
            "data_gap_analysis": {
                "has_gaps": True,
                "can_proceed_with_assumptions": False
            },
            "pending_specialist_requests": [{"query": "test"}]
        }

        result = should_request_specialist(state)
        assert result == "request_specialist"


# =============================================================================
# Discussion Consensus Tests (Mock LLM)
# =============================================================================

class TestConsensusDetection:
    """LLM 기반 합의 감지 테스트"""

    @patch('utils.llm.get_llm')
    def test_llm_consensus_reached(self, mock_get_llm):
        """LLM이 합의 완료로 판정한 경우"""
        from graph.subgraphs import _check_consensus_node
        from utils.schemas import ConsensusResult

        # Mock LLM 응답 설정
        mock_llm = MagicMock()
        mock_consensus_result = ConsensusResult(
            consensus_reached=True,
            confidence=0.9,
            agreed_items=["시장 분석 보강", "경쟁사 3개 추가"],
            unresolved_items=[],
            reasoning="양측이 개선 방향에 합의함"
        )
        mock_llm.with_structured_output.return_value.invoke.return_value = mock_consensus_result
        mock_get_llm.return_value = mock_llm

        # 테스트 State
        state = {
            "discussion_round": 1,
            "discussion_messages": [
                {"role": "reviewer", "content": "시장 분석이 부족합니다", "round": 0},
                {"role": "writer", "content": "경쟁사 3개를 추가하겠습니다", "round": 0},
                {"role": "reviewer", "content": "좋습니다. 진행하세요", "round": 1},
            ]
        }

        result = _check_consensus_node(state)

        assert result.get("consensus_reached") is True
        assert len(result.get("agreed_action_items", [])) >= 1

    @patch('utils.llm.get_llm')
    def test_llm_consensus_not_reached(self, mock_get_llm):
        """LLM이 합의 미완료로 판정한 경우"""
        from graph.subgraphs import _check_consensus_node
        from utils.schemas import ConsensusResult

        # Mock LLM 응답 설정
        mock_llm = MagicMock()
        mock_consensus_result = ConsensusResult(
            consensus_reached=False,
            confidence=0.8,
            agreed_items=[],
            unresolved_items=["재무 계획 구체화 필요"],
            reasoning="Writer가 아직 구체적인 방안을 제시하지 않음"
        )
        mock_llm.with_structured_output.return_value.invoke.return_value = mock_consensus_result
        mock_get_llm.return_value = mock_llm

        state = {
            "discussion_round": 0,
            "discussion_messages": [
                {"role": "reviewer", "content": "재무 계획이 불명확합니다", "round": 0},
                {"role": "writer", "content": "검토해 보겠습니다", "round": 0},
            ]
        }

        result = _check_consensus_node(state)

        assert result.get("consensus_reached") is False

    @patch('utils.llm.get_llm')
    def test_max_rounds_force_consensus(self, mock_get_llm):
        """최대 라운드 도달 시 강제 합의"""
        from graph.subgraphs import _check_consensus_node
        from utils.schemas import ConsensusResult

        # Mock LLM 응답 설정 (합의 미완료로 반환)
        mock_llm = MagicMock()
        mock_consensus_result = ConsensusResult(
            consensus_reached=False,
            confidence=0.5,
            agreed_items=[],
            unresolved_items=["미해결"]
        )
        mock_llm.with_structured_output.return_value.invoke.return_value = mock_consensus_result
        mock_get_llm.return_value = mock_llm

        # DISCUSSION_MAX_ROUNDS(5) 이상으로 설정
        state = {
            "discussion_round": 4,  # 다음 라운드가 5가 됨 (max_rounds 도달)
            "discussion_messages": [
                {"role": "reviewer", "content": "아직 부족합니다", "round": 4},
                {"role": "writer", "content": "개선하겠습니다", "round": 4},
            ]
        }

        result = _check_consensus_node(state)

        # 최대 라운드에서 강제 합의
        assert result.get("consensus_reached") is True


# =============================================================================
# Workflow Integration Tests
# =============================================================================

class TestWorkflowIntegration:
    """워크플로우 통합 테스트"""

    def test_workflow_imports(self):
        """워크플로우 임포트 테스트"""
        from graph.workflow import (
            create_workflow,
            RouteKey,
            DynamicQARoutes,
        )

        assert RouteKey.REQUEST_SPECIALIST == "request_specialist"
        assert RouteKey.WRITE == "write"

    def test_dynamic_qa_nodes_import(self):
        """Dynamic Q&A 노드 임포트 테스트"""
        from graph.nodes.dynamic_qa import (
            analyze_data_gaps,
            should_request_specialist,
            collect_specialist_responses,
        )

        assert callable(analyze_data_gaps)
        assert callable(should_request_specialist)
        assert callable(collect_specialist_responses)

    def test_state_includes_dynamic_qa_fields(self):
        """State에 Dynamic Q&A 필드 포함 확인"""
        from graph.state import create_initial_state

        state = create_initial_state("테스트 서비스 기획")

        assert "data_gap_analysis" in state
        assert "pending_specialist_requests" in state
        assert "specialist_responses" in state
        assert state["pending_specialist_requests"] == []


# =============================================================================
# Prompt Tests
# =============================================================================

class TestDiscussionPrompts:
    """Discussion 프롬프트 테스트"""

    def test_consensus_prompts_exist(self):
        """합의 판정 프롬프트 존재 확인"""
        from prompts.discussion_prompt import (
            CONSENSUS_JUDGE_SYSTEM_PROMPT,
            CONSENSUS_JUDGE_USER_PROMPT,
        )

        assert "합의 판정" in CONSENSUS_JUDGE_SYSTEM_PROMPT
        assert "{discussion_history}" in CONSENSUS_JUDGE_USER_PROMPT

    def test_dynamic_qa_prompts_exist(self):
        """Dynamic Q&A 프롬프트 존재 확인"""
        from prompts.discussion_prompt import (
            DATA_GAP_ANALYSIS_PROMPT,
            SPECIALIST_QUERY_PROMPT,
        )

        assert "데이터 완전성" in DATA_GAP_ANALYSIS_PROMPT
        assert "{specialist_id}" in SPECIALIST_QUERY_PROMPT
