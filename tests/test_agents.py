"""
PlanCraft Agent - 단위 테스트 모듈

각 Agent의 입력-출력을 자동으로 검증하는 pytest 테스트입니다.
Mock State를 사용하여 LLM 호출 없이도 구조적 검증이 가능합니다.

실행 방법:
    pytest tests/test_agents.py -v

테스트 항목:
    - Pydantic 스키마 검증 (AnalysisResult, StructureResult, etc.)
    - State 불변성 검증 (model_copy 패턴)
    - Cross-field validation 검증
    - Fallback 로직 검증
"""

import pytest
from pydantic import ValidationError

# =============================================================================
# 스키마 테스트
# =============================================================================

class TestAnalysisResultSchema:
    """AnalysisResult Pydantic 스키마 테스트"""
    
    def test_valid_analysis_result(self):
        """정상적인 분석 결과 생성"""
        from utils.schemas import AnalysisResult
        
        result = AnalysisResult(
            topic="점심 메뉴 추천 앱",
            purpose="직장인 점심 고민 해결",
            target_users="직장인",
            key_features=["랜덤 추천", "주변 식당 지도"],
            need_more_info=False
        )
        
        assert result.topic == "점심 메뉴 추천 앱"
        assert result.need_more_info is False
        assert len(result.key_features) == 2
    
    def test_need_more_info_auto_options(self):
        """need_more_info=True일 때 options 자동 생성 검증"""
        from utils.schemas import AnalysisResult
        
        # options 없이 need_more_info=True로 생성
        result = AnalysisResult(
            topic="테스트",
            purpose="테스트 목적",
            target_users="테스트 사용자",
            need_more_info=True,
            options=[]  # 빈 options
        )
        
        # model_validator가 자동으로 기본 옵션 생성
        assert len(result.options) >= 1
        assert result.options[0].title == "기본 진행"


class TestJudgeResultSchema:
    """JudgeResult Pydantic 스키마 테스트"""
    
    def test_valid_verdict_values(self):
        """verdict 값 검증 (PASS/REVISE/FAIL)"""
        from utils.schemas import JudgeResult
        
        # PASS 테스트
        result_pass = JudgeResult(overall_score=8, verdict="PASS")
        assert result_pass.verdict == "PASS"
        
        # REVISE 테스트
        result_revise = JudgeResult(overall_score=6, verdict="revise")  # 소문자
        assert result_revise.verdict == "REVISE"  # 자동 대문자 변환
        
        # FAIL 테스트
        result_fail = JudgeResult(overall_score=3, verdict="FAIL")
        assert result_fail.verdict == "FAIL"
    
    def test_invalid_verdict_auto_correction(self):
        """잘못된 verdict 값 자동 보정 검증"""
        from utils.schemas import JudgeResult
        
        # 잘못된 값 -> REVISE로 보정
        result = JudgeResult(overall_score=5, verdict="UNKNOWN")
        assert result.verdict == "REVISE"
    
    def test_score_range_validation(self):
        """점수 범위 검증 (1-10)"""
        from utils.schemas import JudgeResult
        
        # 유효 범위
        result = JudgeResult(overall_score=5, verdict="REVISE")
        assert 1 <= result.overall_score <= 10
        
        # 범위 초과 시 ValidationError
        with pytest.raises(ValidationError):
            JudgeResult(overall_score=11, verdict="PASS")


class TestStructureResultSchema:
    """StructureResult Pydantic 스키마 테스트"""
    
    def test_empty_sections_auto_fallback(self):
        """빈 sections 자동 fallback 검증"""
        from utils.schemas import StructureResult
        
        # 빈 sections로 생성
        result = StructureResult(title="테스트 기획서", sections=[])
        
        # field_validator가 자동으로 기본 섹션 생성
        assert len(result.sections) >= 1
        assert result.sections[0].name == "개요"


# =============================================================================
# State 테스트
# =============================================================================

class TestPlanCraftState:
    """PlanCraftState 상태 관리 테스트"""
    
    def test_state_creation(self):
        """상태 객체 생성 테스트"""
        from graph.state import PlanCraftState
        
        state = PlanCraftState(
            user_input="테스트 입력",
            current_step="start"
        )
        
        assert state.user_input == "테스트 입력"
        assert state.current_step == "start"
        assert state.need_more_info is False
    
    def test_state_immutability(self):
        """상태 불변성 테스트 (model_copy 패턴)"""
        from graph.state import PlanCraftState
        
        original = PlanCraftState(
            user_input="원본",
            current_step="start"
        )
        
        # model_copy로 새 상태 생성
        updated = original.model_copy(update={"current_step": "analyze"})
        
        # 원본 상태는 변경되지 않음
        assert original.current_step == "start"
        assert updated.current_step == "analyze"
    
    def test_state_with_analysis(self):
        """분석 결과 포함 상태 테스트"""
        from graph.state import PlanCraftState
        from utils.schemas import AnalysisResult
        
        analysis = AnalysisResult(
            topic="테스트 앱",
            purpose="테스트",
            target_users="테스터",
            need_more_info=False
        )
        
        state = PlanCraftState(
            user_input="테스트",
            analysis=analysis,
            current_step="analyze"
        )
        
        assert state.analysis is not None
        assert state.analysis.topic == "테스트 앱"


# =============================================================================
# 통합 테스트 (Mock 기반)
# =============================================================================

class TestAgentIntegration:
    """Agent 통합 테스트 (실제 LLM 호출 없이)"""
    
    def test_state_flow_simulation(self):
        """상태 흐름 시뮬레이션"""
        from graph.state import PlanCraftState
        from utils.schemas import AnalysisResult, StructureResult, SectionStructure
        
        # 1. 초기 상태
        state = PlanCraftState(
            user_input="점심 추천 앱",
            current_step="start"
        )
        
        # 2. 분석 완료 상태
        analysis = AnalysisResult(
            topic="점심 메뉴 추천 앱",
            purpose="직장인 점심 고민 해결",
            target_users="직장인",
            key_features=["랜덤 추천"],
            need_more_info=False
        )
        state = state.model_copy(update={
            "analysis": analysis,
            "current_step": "analyze"
        })
        
        # 3. 구조 설계 완료 상태
        structure = StructureResult(
            title="점심 추천 앱 기획서",
            sections=[
                SectionStructure(id=1, name="개요", description="앱 소개", key_points=[])
            ]
        )
        state = state.model_copy(update={
            "structure": structure,
            "current_step": "structure"
        })
        
        # 검증
        assert state.analysis.topic == "점심 메뉴 추천 앱"
        assert state.structure.title == "점심 추천 앱 기획서"
        assert len(state.structure.sections) == 1


# =============================================================================
# Sub-graph 테스트
# =============================================================================

class TestSubgraphs:
    """Sub-graph 구조 테스트"""
    
    def test_context_subgraph_creation(self):
        """Context Sub-graph 생성 테스트"""
        from graph.subgraphs import create_context_subgraph
        
        subgraph = create_context_subgraph()
        
        # 노드가 등록되었는지 확인
        assert "rag_retrieve" in subgraph.nodes
        assert "web_fetch" in subgraph.nodes
    
    def test_generation_subgraph_creation(self):
        """Generation Sub-graph 생성 테스트"""
        from graph.subgraphs import create_generation_subgraph
        
        subgraph = create_generation_subgraph()
        
        # 노드가 등록되었는지 확인
        assert "analyze" in subgraph.nodes
        assert "structure" in subgraph.nodes
        assert "write" in subgraph.nodes
    
    def test_qa_subgraph_creation(self):
        """QA Sub-graph 생성 테스트"""
        from graph.subgraphs import create_qa_subgraph
        
        subgraph = create_qa_subgraph()
        
        # 노드가 등록되었는지 확인
        assert "review" in subgraph.nodes
        assert "refine" in subgraph.nodes
        assert "format" in subgraph.nodes
    
    def test_subgraph_workflow_creation(self):
        """Sub-graph 패턴 워크플로우 생성 테스트"""
        from graph.workflow import create_subgraph_workflow
        
        workflow = create_subgraph_workflow()
        
        # Sub-graph 노드가 등록되었는지 확인
        assert "context_gathering" in workflow.nodes
        assert "content_generation" in workflow.nodes
        assert "quality_assurance" in workflow.nodes


# =============================================================================
# 실행
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
