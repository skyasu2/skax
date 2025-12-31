"""
PlanCraft Workflow Routing Tests

워크플로우 분기 및 라우팅 로직을 검증합니다.
RunnableBranch 패턴과 휴먼 인터럽트 분기 조건을 테스트합니다.
"""

import pytest
from graph.state import PlanCraftState
from utils.schemas import AnalysisResult

class TestWorkflowRouting:
    """워크플로우 라우팅 및 분기 테스트"""
    
    def test_should_ask_user_routing(self):
        """should_ask_user 라우팅 함수 검증"""
        from graph.workflow import should_ask_user
        
        # 1. 추가 정보 필요한 경우 -> option_pause
        state_need_info = PlanCraftState(
            user_input="모호한 요청",
            need_more_info=True,
            current_step="analyze"
        )
        assert should_ask_user(state_need_info) == "option_pause"
        
        # 2. 일반 질의인 경우 -> general_response
        analysis_general = AnalysisResult(
            topic="인사", purpose="", target_users="",
            is_general_query=True
        )
        state_general = PlanCraftState(
            user_input="안녕하세요",
            analysis=analysis_general,
            need_more_info=False,
            current_step="analyze"
        )
        assert should_ask_user(state_general) == "general_response"
        
        # 3. 정상 기획 요청 -> continue
        analysis_plan = AnalysisResult(
            topic="앱 기획", purpose="테스트", target_users="유저",
            is_general_query=False, need_more_info=False
        )
        state_plan = PlanCraftState(
            user_input="앱 만들어줘",
            analysis=analysis_plan,
            need_more_info=False,
            current_step="analyze"
        )
        assert should_ask_user(state_plan) == "continue"

    def test_runnable_branch_logic(self):
        """RunnableBranch 조건 함수 단위 테스트"""
        from graph.workflow import (
            is_human_interrupt_required,
            is_general_query,
            is_plan_generation_ready
        )
        
        # Setup states
        state_interrupt = PlanCraftState(user_input=".", need_more_info=True)
        state_general = PlanCraftState(
            user_input=".", 
            analysis=AnalysisResult(topic="", purpose="", target_users="", is_general_query=True)
        )
        state_ready = PlanCraftState(
            user_input=".", 
            need_more_info=False,
            analysis=AnalysisResult(topic="", purpose="", target_users="", is_general_query=False)
        )
        
        # Check logic
        assert is_human_interrupt_required(state_interrupt) is True
        assert is_human_interrupt_required(state_ready) is False
        
        assert is_general_query(state_general) is True
        assert is_general_query(state_ready) is False
        
        assert is_plan_generation_ready(state_ready) is True
        assert is_plan_generation_ready(state_interrupt) is False

    def test_interrupt_payload_creation(self):
        """인터럽트 페이로드 생성 유틸리티 검증"""
        from graph.interrupt_utils import create_interrupt_payload, create_option_interrupt
        from utils.schemas import OptionChoice
        
        # 1. 기본 Payload 생성
        options = [OptionChoice(title="A", description="Desc A")]
        payload = create_interrupt_payload(
            question="질문",
            options=options
        )
        assert payload["question"] == "질문"
        assert payload["options"][0]["title"] == "A"
        assert payload["type"] == "option"
        
        # 2. State 기반 Option Interrupt 생성
        state = PlanCraftState(
            user_input="test",
            option_question="어떤 앱인가요?",
            options=[OptionChoice(title="웹", description="Web App")],
            need_more_info=True
        )
        
        opt_payload = create_option_interrupt(state)
        assert opt_payload["question"] == "어떤 앱인가요?"
        assert opt_payload["options"][0]["title"] == "웹"
        assert opt_payload["data"]["need_more_info"] is True

    def test_handle_user_response(self):
        """사용자 응답 처리 및 상태 업데이트 검증"""
        from graph.interrupt_utils import handle_user_response
        
        initial_state = PlanCraftState(
            user_input="초기 요청",
            need_more_info=True,
            option_question="질문",
            options=[{"title": "옵션1", "description": "설명1"}]
        )
        
        # 사용자 응답 (옵션 선택)
        response = {
            "selected_option": {"title": "옵션1", "description": "설명1"}
        }
        
        new_state = handle_user_response(initial_state, response)

        # 검증: 입력 업데이트, 플래그 초기화 (dict-access 방식)
        assert "초기 요청" in new_state.get("user_input", "")
        assert "[선택: 옵션1 - 설명1]" in new_state.get("user_input", "")
        assert new_state.get("need_more_info") is False
        assert new_state.get("option_question") is None

class TestPresetBasedValidation:
    """프리셋 기반 섹션 수 검증 테스트 (방안 D 구현 검증)"""

    def test_preset_min_sections_values(self):
        """각 프리셋별 최소 섹션 수 설정값 검증"""
        from utils.settings import get_preset, GENERATION_PRESETS

        # fast: 7개, balanced: 9개, quality: 10개
        assert get_preset("fast").min_sections == 7
        assert get_preset("balanced").min_sections == 9
        assert get_preset("quality").min_sections == 10

        # structurer_max_retries는 모든 모드에서 2회 고정
        for preset_key in GENERATION_PRESETS:
            preset = get_preset(preset_key)
            assert preset.structurer_max_retries == 2, \
                f"{preset_key} 모드의 structurer_max_retries가 2가 아님"

    def test_preset_writer_max_retries(self):
        """Writer Self-Correction 재시도 횟수 검증"""
        from utils.settings import get_preset

        # fast: 1회, balanced: 2회, quality: 3회
        assert get_preset("fast").writer_max_retries == 1
        assert get_preset("balanced").writer_max_retries == 2
        assert get_preset("quality").writer_max_retries == 3

    def test_preset_effective_settings(self):
        """프리셋 적용된 설정값 반환 검증"""
        from utils.settings import settings

        # 기본 프리셋 (balanced)으로 효과적인 설정 확인
        settings.active_preset = "balanced"
        effective = settings.get_effective_settings()

        assert effective["min_sections"] == 9
        assert effective["structurer_max_retries"] == 2
        assert effective["writer_max_retries"] == 2


class TestHITLMetaFields:
    """HITL 메타필드 기록 검증 테스트"""

    def test_state_hitl_meta_fields_exist(self):
        """State에 HITL 메타필드가 정의되어 있는지 검증"""
        from graph.state import create_initial_state

        state = create_initial_state("테스트 입력")

        # 메타필드 존재 확인 (Optional이므로 None일 수 있음)
        assert "last_pause_type" in state or state.get("last_pause_type") is None
        assert "last_resume_value" in state or state.get("last_resume_value") is None
        assert "last_human_event" in state or state.get("last_human_event") is None

    def test_handle_user_response_records_meta(self):
        """handle_user_response가 메타필드를 기록하는지 검증"""
        from graph.interrupt_utils import handle_user_response
        from graph.state import create_initial_state, update_state

        # 초기 상태 설정
        state = create_initial_state("모호한 요청")
        state = update_state(state,
            need_more_info=True,
            option_question="어떤 앱인가요?",
            options=[{"title": "웹앱", "description": "Web Application"}]
        )

        # 사용자 응답 처리
        response = {
            "selected_option": {"title": "웹앱", "description": "Web Application"}
        }

        new_state = handle_user_response(state, response)

        # 메타필드 기록 검증
        assert new_state.get("last_pause_type") == "option"
        assert new_state.get("last_resume_value") is not None

        # step_history에 HUMAN_RESPONSE 로그 존재 확인
        history = new_state.get("step_history", [])
        human_logs = [h for h in history if h.get("event_type") == "HUMAN_RESPONSE"]
        assert len(human_logs) > 0, "HUMAN_RESPONSE 로그가 기록되어야 함"

    def test_interrupt_payload_tracking_fields(self):
        """인터럽트 페이로드에 추적 필드가 포함되는지 검증"""
        from graph.interrupt_types import InterruptFactory, InterruptType, InterruptOption

        payload = InterruptFactory.create(
            InterruptType.OPTION,
            question="테스트 질문",
            options=[InterruptOption(title="A", description="설명A")],
            node_ref="test_node"
        )

        # 추적 필드 존재 확인
        assert payload.get("node_ref") == "test_node"
        assert payload.get("event_id") is not None  # UUID 자동 생성
        assert payload.get("timestamp") is not None  # ISO 시각 자동 생성


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
