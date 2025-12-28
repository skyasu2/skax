
import pytest
from graph.state import PlanCraftState, create_initial_state, PlanCraftInput, update_state

from graph.interrupt_utils import create_option_interrupt, handle_user_response
from utils.schemas import OptionChoice, InterruptPayload

def test_interrupt_payload_creation():
    """InterruptPayload 생성 로직 검증"""
    state = create_initial_state("test")
    # TypedDict dict-access 방식으로 업데이트
    state = update_state(state,
        option_question="테스트 질문",
        options=[
            OptionChoice(title="옵션1", description="설명1"),
            {"title": "옵션2", "description": "설명2"}  # Dict 호환성 테스트
        ],
        input_schema_name="MockSchema"
    )

    payload_dict = create_option_interrupt(state)

    # Dict로 반환되어야 함
    assert isinstance(payload_dict, dict)

    # 필드 검증
    assert payload_dict["question"] == "테스트 질문"
    assert len(payload_dict["options"]) == 2
    assert payload_dict["type"] == "form"  # schema가 있으므로 form
    assert payload_dict["input_schema_name"] == "MockSchema"
    assert payload_dict["options"][0]["title"] == "옵션1"
    assert payload_dict["options"][1]["title"] == "옵션2"

def test_resume_handling_form():
    """Form 데이터 형태의 Resume 처리 검증"""
    state = create_initial_state("test")
    state = update_state(state,
        input_schema_name="SomeSchema",
        user_input="기존 입력"
    )

    # 폼 응답 시뮬레이션
    resume_data = {"field1": "value1", "field2": "value2"}

    new_state = handle_user_response(state, resume_data)

    assert "field1: value1" in new_state.get("user_input", "")
    assert new_state.get("input_schema_name") is None
    assert new_state.get("need_more_info") is False

def test_resume_handling_option():
    """옵션 선택 형태의 Resume 처리 검증"""
    state = create_initial_state("test")
    state = update_state(state, user_input="기존 입력")

    # 옵션 선택 시뮬레이션
    resume_data = {"selected_option": {"title": "선택1", "description": "설명"}}

    new_state = handle_user_response(state, resume_data)

    assert "[선택: 선택1 - 설명]" in new_state.get("user_input", "")
    assert new_state.get("need_more_info") is False
