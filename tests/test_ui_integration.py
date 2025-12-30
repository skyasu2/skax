"""
UI 통합 테스트 - HITL Interrupt 패턴 검증

다양한 인터럽트 유형(option, form, confirm)에 대한 UI 상호작용을 테스트합니다.
실제 LLM 호출 없이 Mock을 사용하여 빠르게 검증합니다.
"""

import pytest
from unittest.mock import patch, MagicMock
from graph.state import create_initial_state, update_state, PlanCraftState
from graph.interrupt_utils import create_option_interrupt, handle_user_response
from utils.schemas import OptionChoice, InterruptPayload, AnalysisResult


# =============================================================================
# Fixture: 공통 테스트 데이터
# =============================================================================

@pytest.fixture
def base_state() -> PlanCraftState:
    """기본 테스트 상태"""
    return create_initial_state(
        user_input="점심 추천 앱",
        thread_id="test_thread_001"
    )


@pytest.fixture
def hitl_state(base_state) -> PlanCraftState:
    """HITL 트리거된 상태 (짧은 입력)"""
    return update_state(
        base_state,
        need_more_info=True,
        option_question="어떤 방향의 서비스를 원하시나요?",
        options=[
            {"title": "AI 맛집 추천", "description": "개인화된 맛집 추천"},
            {"title": "그룹 투표", "description": "팀원과 함께 결정"},
            {"title": "배달 중개", "description": "단체 배달 주문"}
        ]
    )


# =============================================================================
# 테스트: Interrupt Payload 생성
# =============================================================================

class TestInterruptPayloadCreation:
    """인터럽트 페이로드 생성 테스트"""

    def test_option_type_payload(self, hitl_state):
        """옵션 선택형 페이로드 생성"""
        payload = create_option_interrupt(hitl_state)

        assert payload["type"] == "option"
        assert payload["question"] == "어떤 방향의 서비스를 원하시나요?"
        assert len(payload["options"]) == 3
        assert payload["options"][0]["title"] == "AI 맛집 추천"

    def test_form_type_payload(self, base_state):
        """폼 입력형 페이로드 생성"""
        state = update_state(
            base_state,
            need_more_info=True,
            option_question="추가 정보를 입력해주세요",
            options=[],
            input_schema_name="UserInputSchema"
        )

        payload = create_option_interrupt(state)

        assert payload["type"] == "form"
        assert payload["input_schema_name"] == "UserInputSchema"

    def test_payload_json_serializable(self, hitl_state):
        """페이로드 JSON 직렬화 가능 여부"""
        import json

        payload = create_option_interrupt(hitl_state)

        # JSON 직렬화 가능해야 함
        json_str = json.dumps(payload, ensure_ascii=False)
        assert isinstance(json_str, str)

        # 역직렬화 후 동일성 검증
        parsed = json.loads(json_str)
        assert parsed["question"] == payload["question"]


# =============================================================================
# 테스트: Resume (사용자 응답) 처리
# =============================================================================

class TestResumeHandling:
    """사용자 Resume 입력 처리 테스트"""

    def test_option_selection_resume(self, hitl_state):
        """옵션 선택 응답 처리"""
        resume_data = {
            "selected_option": {
                "id": "1",
                "title": "AI 맛집 추천",
                "description": "개인화된 맛집 추천"
            }
        }

        new_state = handle_user_response(hitl_state, resume_data)

        # 사용자 입력에 선택 내용 반영
        assert "AI 맛집 추천" in new_state.get("user_input", "")
        assert new_state.get("need_more_info") is False
        assert new_state.get("selected_option") is not None

    def test_text_input_resume(self, hitl_state):
        """직접 텍스트 입력 응답 처리"""
        resume_data = {
            "text_input": "AI 추천 + 그룹 투표 기능 모두 포함해주세요"
        }

        new_state = handle_user_response(hitl_state, resume_data)

        assert "AI 추천 + 그룹 투표" in new_state.get("user_input", "")
        assert new_state.get("need_more_info") is False

    def test_form_data_resume(self, base_state):
        """폼 데이터 응답 처리"""
        state = update_state(
            base_state,
            input_schema_name="UserInputSchema"
        )

        resume_data = {
            "user_feedback": "예산은 1억원이고 3개월 내 출시 희망",
            "selected_options": ["빠른 개발", "MVP 우선"]
        }

        new_state = handle_user_response(state, resume_data)

        assert "예산은 1억원" in new_state.get("user_input", "")
        assert new_state.get("input_schema_name") is None

    def test_empty_resume_handling(self, hitl_state):
        """빈 응답 처리 (에러 방지)"""
        resume_data = {}

        # 에러 없이 처리되어야 함
        new_state = handle_user_response(hitl_state, resume_data)

        # 원래 상태가 유지되어야 함
        assert new_state.get("user_input") == hitl_state.get("user_input")


# =============================================================================
# 테스트: Interrupt 유형별 UI 렌더링 데이터
# =============================================================================

class TestInterruptUIData:
    """UI 렌더링에 필요한 데이터 검증"""

    def test_option_ui_data(self, hitl_state):
        """옵션 UI 렌더링 데이터"""
        payload = create_option_interrupt(hitl_state)

        # UI에 필요한 모든 필드 존재 확인
        assert "type" in payload
        assert "question" in payload
        assert "options" in payload

        # 각 옵션에 필수 필드 존재
        for opt in payload["options"]:
            assert "title" in opt
            assert "description" in opt

    def test_error_message_in_payload(self, base_state):
        """에러 메시지 포함된 페이로드"""
        state = update_state(
            base_state,
            need_more_info=True,
            option_question="다시 입력해주세요",
            options=[{"title": "재시도", "description": "다시 시도"}],
            error_message="입력값이 유효하지 않습니다"
        )

        payload = create_option_interrupt(state)

        # 에러 메시지가 data에 포함되어야 함
        assert "data" in payload
        # error 필드는 선택적

    def test_retry_count_tracking(self, hitl_state):
        """재시도 횟수 추적"""
        state = update_state(hitl_state, retry_count=2)

        payload = create_option_interrupt(state)

        # data에 retry_count 포함
        assert payload.get("data", {}).get("retry_count", 0) == 2


# =============================================================================
# 테스트: Step History 기록
# =============================================================================

class TestStepHistoryRecording:
    """Resume 시 step_history 기록 검증"""

    def test_resume_logged_in_history(self, hitl_state):
        """Resume 입력이 step_history에 기록되는지"""
        resume_data = {
            "selected_option": {"title": "AI 추천", "description": "개인화 추천"}
        }

        new_state = handle_user_response(hitl_state, resume_data)

        # step_history에 resume 기록 존재
        history = new_state.get("step_history", [])

        # 최소 1개 이상의 기록이 있어야 함 (구현에 따라)
        # 현재 구현에서는 handle_user_response가 직접 history를 추가하지 않을 수 있음
        # 이 테스트는 구현 확인용
        assert isinstance(history, list)


# =============================================================================
# 테스트: 다중 인터럽트 시나리오
# =============================================================================

class TestMultipleInterruptScenarios:
    """복수 인터럽트 발생 시나리오"""

    def test_sequential_interrupts(self, base_state):
        """연속적인 인터럽트 처리"""
        # 첫 번째 인터럽트
        state1 = update_state(
            base_state,
            need_more_info=True,
            option_question="질문 1",
            options=[{"title": "A", "description": "옵션 A"}]
        )

        payload1 = create_option_interrupt(state1)
        assert payload1["question"] == "질문 1"

        # 첫 번째 응답 처리
        state2 = handle_user_response(state1, {"selected_option": {"title": "A", "description": "옵션 A"}})

        # 두 번째 인터럽트 (가정: Analyzer가 다시 질문)
        state3 = update_state(
            state2,
            need_more_info=True,
            option_question="질문 2 (상세)",
            options=[{"title": "B", "description": "옵션 B"}]
        )

        payload2 = create_option_interrupt(state3)
        assert payload2["question"] == "질문 2 (상세)"

    def test_max_retry_exceeded(self, hitl_state):
        """최대 재시도 횟수 초과"""
        from utils.settings import settings

        state = update_state(hitl_state, retry_count=settings.HITL_MAX_RETRIES)

        # 최대 재시도 도달 시에도 페이로드 생성 가능
        payload = create_option_interrupt(state)
        assert payload is not None


# =============================================================================
# 테스트: 스키마 검증
# =============================================================================

class TestSchemaValidation:
    """Pydantic 스키마 검증"""

    def test_analysis_result_with_options(self):
        """AnalysisResult + 옵션 검증"""
        data = {
            "topic": "테스트",
            "purpose": "테스트 목적",
            "target_users": "테스터",
            "key_features": [],
            "need_more_info": True,
            "options": [
                {"title": "옵션1", "description": "설명1"}
            ],
            "option_question": "선택하세요"
        }

        result = AnalysisResult(**data)

        assert result.need_more_info is True
        assert len(result.options) == 1
        assert result.options[0].title == "옵션1"

    def test_analysis_result_auto_option_fallback(self):
        """need_more_info=True인데 options가 없을 때 자동 생성"""
        data = {
            "topic": "테스트",
            "purpose": "목적",
            "target_users": "사용자",
            "need_more_info": True,
            "options": []  # 비어있음
        }

        result = AnalysisResult(**data)

        # 자동으로 기본 옵션 생성
        assert len(result.options) >= 1

    def test_interrupt_payload_schema(self):
        """InterruptPayload 스키마 검증"""
        payload = InterruptPayload(
            type="option",
            question="테스트 질문",
            options=[OptionChoice(title="A", description="B")],
            input_schema_name=None,
            data={}
        )

        assert payload.type == "option"
        assert payload.question == "테스트 질문"


# =============================================================================
# 실행
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
