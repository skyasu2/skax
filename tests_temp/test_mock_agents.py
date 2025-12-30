
import pytest
from unittest.mock import MagicMock, patch
from graph.state import create_initial_state, update_state
from utils.schemas import AnalysisResult, StructureResult, SectionStructure, DraftResult, SectionContent

class TestMockAgents:
    """
    [Local Test] Mock LLM을 활용한 에이전트 로직 검증
    API Key 없이 로컬에서 agent.run() 함수의 동작을 테스트합니다.
    """

    @patch('agents.analyzer.analyzer_llm')
    def test_analyzer_mock(self, mock_llm):
        """Analyzer 에이전트 Mock 테스트"""
        print("\n[Test] Analyzer Mock Run")
        
        # 1. Mock Response 설정
        mock_output = AnalysisResult(
            topic="Mock AI App",
            purpose="For Testing",
            target_users="Tester",
            key_features=["Feature A", "Feature B"],
            need_more_info=False
        )
        # invoke 호출 시 Pydantic 객체 반환
        mock_llm.invoke.return_value = mock_output
        
        # 2. 실행
        from agents.analyzer import run
        state = create_initial_state("AI 앱 기획해줘")
        new_state = run(state)
        
        # 3. 검증
        analysis = new_state.get("analysis")
        assert analysis is not None
        assert analysis["topic"] == "Mock AI App"
        assert len(analysis["key_features"]) == 2
        print("✅ Analyzer Output Verified")

    @patch('agents.structurer.structurer_llm')
    def test_structurer_mock(self, mock_llm):
        """Structurer 에이전트 Mock 테스트"""
        print("\n[Test] Structurer Mock Run")
        
        # 1. Mock Response 설정
        mock_output = StructureResult(
            title="Mock Plan",
            sections=[
                SectionStructure(id=1, name="Intro", description="Desc 1", key_points=[]),
                SectionStructure(id=2, name="Core", description="Desc 2", key_points=[])
            ]
        )
        mock_llm.invoke.return_value = mock_output
        
        # 2. 상태 준비 (Analyzer 통과 가정)
        state = create_initial_state("AI 앱")
        state = update_state(state, analysis={
            "topic": "Mock AI App", 
            "key_features": ["A"]
        })
        
        # 3. 실행
        from agents.structurer import run
        new_state = run(state)
        
        # 4. 검증
        structure = new_state.get("structure")
        assert structure is not None
        assert structure["title"] == "Mock Plan"
        assert len(structure["sections"]) == 2
        print("✅ Structurer Output Verified")

    @patch('agents.writer.writer_llm')
    def test_writer_mock(self, mock_llm):
        """Writer 에이전트 Mock 테스트 (Side Effect 활용)"""
        print("\n[Test] Writer Mock Run")
        
        mock_output = DraftResult(
            sections=[
                SectionContent(id=1, name="Intro", content="# Intro\nMock Content 1"),
                SectionContent(id=2, name="Core", content="# Core\nMock Content 2")
            ]
        )
        mock_llm.invoke.return_value = mock_output
        
        # 상태 준비
        state = create_initial_state("AI 앱")
        state = update_state(state, 
            analysis={"topic": "Mock", "key_features": []},
            structure={"title": "Plan", "sections": [
                {"id": 1, "name": "Intro", "description": "D1", "key_points": []},
                {"id": 2, "name": "Core", "description": "D2", "key_points": []}
            ]}
        )
        
        # 실행
        from agents.writer import run
        new_state = run(state)
        
        # 검증
        draft = new_state.get("draft")
        assert draft is not None
        assert len(draft["sections"]) == 2
        assert "Mock Content 1" in draft["sections"][0]["content"]
        print("✅ Writer Output Verified")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
