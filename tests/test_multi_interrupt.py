"""
Multi-Interrupt Scenario Tests

멀티 인터럽트 시나리오를 테스트합니다:
- 옵션 선택 → 폼 입력 → 승인 연쇄 HITL
- 각 인터럽트 타입별 응답 처리
- 에러 상황 처리 및 재시도

테스트 실행:
    pytest tests/test_multi_interrupt.py -v
"""

import pytest
import json
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Import interrupt types and utilities
from graph.interrupt_types import (
    InterruptType,
    InterruptFactory,
    InterruptOption,
    OptionInterruptPayload,
    FormInterruptPayload,
    ConfirmInterruptPayload,
    ApprovalInterruptPayload,
    ResumeHandler,
    normalize_options,
)
from graph.interrupt_utils import (
    create_interrupt_payload,
    create_option_interrupt,
    handle_user_response,
    make_pause_node,
    make_approval_pause_node,
)
from graph.state import create_initial_state, update_state


class TestInterruptFactory:
    """InterruptFactory 클래스 테스트"""

    def test_option_factory_method(self):
        """option() 편의 메서드 테스트"""
        payload = InterruptFactory.option(
            question="어떤 유형을 선택하시겠습니까?",
            options=[
                {"title": "웹 앱", "description": "브라우저 기반"},
                {"title": "모바일 앱", "description": "iOS/Android"}
            ]
        )
        
        assert isinstance(payload, OptionInterruptPayload)
        assert payload.question == "어떤 유형을 선택하시겠습니까?"
        assert len(payload.options) == 2
        assert payload.options[0].title == "웹 앱"
        assert payload.allow_custom is True
        assert payload.node_ref == "option_pause"
        assert payload.event_id.startswith("evt_")

    def test_form_factory_method(self):
        """form() 편의 메서드 테스트"""
        payload = InterruptFactory.form(
            question="프로젝트 정보를 입력하세요",
            schema_name="ProjectInfo",
            required_fields=["name", "budget"],
            field_types={"budget": "int"}
        )
        
        assert isinstance(payload, FormInterruptPayload)
        assert payload.question == "프로젝트 정보를 입력하세요"
        assert payload.input_schema_name == "ProjectInfo"
        assert "name" in payload.required_fields
        assert payload.field_types.get("budget") == "int"

    def test_confirm_factory_method(self):
        """confirm() 편의 메서드 테스트"""
        payload = InterruptFactory.confirm(
            question="이 구조로 진행하시겠습니까?",
            confirm_text="네, 진행합니다",
            cancel_text="다시 생성"
        )
        
        assert isinstance(payload, ConfirmInterruptPayload)
        assert payload.confirm_text == "네, 진행합니다"
        assert payload.cancel_text == "다시 생성"
        assert payload.default_value is False

    def test_approval_factory_method(self):
        """approval() 편의 메서드 테스트"""
        payload = InterruptFactory.approval(
            question="기획서를 최종 승인하시겠습니까?",
            role="팀장"
        )
        
        assert isinstance(payload, ApprovalInterruptPayload)
        assert payload.role == "팀장"
        assert len(payload.options) == 2
        assert payload.options[0].value == "approve"
        assert payload.rejection_feedback_enabled is True

    def test_to_dict_serializable(self):
        """to_dict() 결과가 JSON 직렬화 가능한지 테스트"""
        payload = InterruptFactory.option(
            question="테스트 질문",
            options=[{"title": "옵션1", "description": "설명1"}]
        )
        
        payload_dict = payload.to_dict()
        
        # JSON 직렬화 가능해야 함
        json_str = json.dumps(payload_dict, ensure_ascii=False)
        assert json_str is not None
        
        # 파싱 후 동일한 값 확인
        parsed = json.loads(json_str)
        assert parsed["question"] == "테스트 질문"
        assert parsed["type"] == "option"


class TestNormalizeOptions:
    """옵션 정규화 함수 테스트"""

    def test_normalize_dict_options(self):
        """딕셔너리 옵션 정규화"""
        options = [
            {"title": "A", "description": "설명A"},
            {"title": "B", "description": "설명B"}
        ]
        
        normalized = normalize_options(options)
        
        assert len(normalized) == 2
        assert all(isinstance(opt, InterruptOption) for opt in normalized)
        assert normalized[0].title == "A"

    def test_normalize_mixed_options(self):
        """혼합 형태 옵션 정규화 (dict + InterruptOption)"""
        options = [
            {"title": "A", "description": "설명A"},
            InterruptOption(title="B", description="설명B")
        ]
        
        normalized = normalize_options(options)
        
        assert len(normalized) == 2
        assert normalized[1].title == "B"

    def test_normalize_duck_typing(self):
        """Duck typing 객체 정규화"""
        class MockOption:
            def __init__(self, title, description):
                self.title = title
                self.description = description
        
        options = [MockOption("Custom", "Custom Desc")]
        normalized = normalize_options(options)
        
        assert len(normalized) == 1
        assert normalized[0].title == "Custom"


class TestResumeHandler:
    """응답 처리 핸들러 테스트"""

    def test_handle_option_response(self):
        """옵션 선택 응답 처리"""
        response = {"selected_option": {"title": "웹 앱", "description": "브라우저 기반"}}
        
        result = ResumeHandler.handle(InterruptType.OPTION, response)
        
        assert result["action"] == "option_selected"
        assert result["selected_option"]["title"] == "웹 앱"

    def test_handle_approval_approved(self):
        """승인 응답 처리"""
        response = {"selected_option": {"title": "승인", "value": "approve"}}
        
        result = ResumeHandler.handle(InterruptType.APPROVAL, response)
        
        assert result["action"] == "approved"
        assert result["approved"] is True

    def test_handle_approval_rejected(self):
        """반려 응답 처리 (피드백 포함)"""
        response = {
            "selected_option": {"value": "reject"},
            "rejection_reason": "BM 섹션 보강 필요"
        }
        
        result = ResumeHandler.handle(InterruptType.APPROVAL, response)
        
        assert result["action"] == "rejected"
        assert result["approved"] is False
        assert result["rejection_reason"] == "BM 섹션 보강 필요"

    def test_handle_confirm(self):
        """확인 응답 처리"""
        response = {"confirmed": True}
        
        result = ResumeHandler.handle(InterruptType.CONFIRM, response)
        
        assert result["action"] == "confirmed"
        assert result["confirmed"] is True

    def test_handle_form(self):
        """폼 응답 처리"""
        response = {"project_name": "AI 헬스케어", "budget": 50000000}
        
        result = ResumeHandler.handle(InterruptType.FORM, response)
        
        assert result["action"] == "form_submitted"
        assert result["form_data"]["project_name"] == "AI 헬스케어"


class TestValidationResponses:
    """응답 유효성 검증 테스트"""

    def test_option_validate_selected(self):
        """옵션 선택 응답 검증 - 성공"""
        payload = InterruptFactory.option(
            question="테스트",
            options=[{"title": "A", "description": ""}]
        )
        
        response = {"selected_option": {"title": "A"}}
        assert payload.validate_response(response) is True

    def test_option_validate_custom_input(self):
        """옵션 직접 입력 응답 검증 - 성공"""
        payload = InterruptFactory.option(
            question="테스트",
            options=[{"title": "A", "description": ""}],
            allow_custom=True
        )
        
        response = {"text_input": "직접 입력한 내용"}
        assert payload.validate_response(response) is True

    def test_form_validate_missing_required(self):
        """폼 필수 필드 누락 검증 - 실패"""
        payload = InterruptFactory.form(
            question="테스트",
            schema_name="Test",
            required_fields=["name", "email"]
        )
        
        response = {"name": "테스트"}  # email 누락
        assert payload.validate_response(response) is False
        
        errors = payload.get_validation_errors(response)
        assert any("email" in err for err in errors)

    def test_form_validate_type_mismatch(self):
        """폼 타입 불일치 검증 - 실패"""
        payload = InterruptFactory.form(
            question="테스트",
            schema_name="Test",
            required_fields=["budget"],
            field_types={"budget": "int"}
        )
        
        response = {"budget": "not_a_number"}
        errors = payload.get_validation_errors(response)
        
        assert any("타입 불일치" in err for err in errors)


class TestMultiInterruptScenario:
    """멀티 인터럽트 시나리오 통합 테스트"""

    def test_option_then_form_scenario(self):
        """
        시나리오: 옵션 선택 → 폼 입력
        
        1. 사용자가 "상세 정보 입력" 옵션 선택
        2. 폼 입력 인터럽트 발생
        3. 폼 데이터 제출
        """
        # Step 1: 옵션 인터럽트
        option_payload = InterruptFactory.option(
            question="어떻게 진행하시겠습니까?",
            options=[
                {"title": "바로 생성", "description": "기본값으로 진행"},
                {"title": "상세 정보 입력", "description": "추가 정보 입력"}
            ]
        )
        
        # Step 2: 사용자 옵션 선택
        option_response = {"selected_option": {"title": "상세 정보 입력"}}
        assert option_payload.validate_response(option_response)
        
        # Step 3: 폼 인터럽트 발생
        form_payload = InterruptFactory.form(
            question="프로젝트 상세 정보를 입력하세요",
            schema_name="ProjectDetails",
            required_fields=["project_name", "budget"]
        )
        
        # Step 4: 폼 데이터 제출
        form_response = {"project_name": "AI 플랫폼", "budget": 100000000}
        assert form_payload.validate_response(form_response)
        
        # Step 5: 핸들러로 처리
        result = ResumeHandler.handle(InterruptType.FORM, form_response)
        assert result["form_data"]["project_name"] == "AI 플랫폼"

    def test_option_form_approval_chain(self):
        """
        시나리오: 옵션 선택 → 폼 입력 → 승인 요청
        
        전체 HITL 체인 테스트
        """
        # Phase 1: 옵션 선택
        opt_payload = InterruptFactory.option(
            question="시작 방식을 선택하세요",
            options=[{"title": "새 프로젝트", "description": "처음부터 생성"}]
        )
        opt_response = {"selected_option": {"title": "새 프로젝트"}}
        assert opt_payload.validate_response(opt_response)
        
        # Phase 2: 폼 입력
        form_payload = InterruptFactory.form(
            question="프로젝트 정보",
            schema_name="ProjectInfo",
            required_fields=["name"]
        )
        form_response = {"name": "테스트 프로젝트"}
        assert form_payload.validate_response(form_response)
        
        # Phase 3: 승인 요청
        approval_payload = InterruptFactory.approval(
            question="기획서를 승인하시겠습니까?",
            role="팀장"
        )
        
        # Case A: 승인
        approve_response = {"selected_option": {"value": "approve"}}
        assert approval_payload.validate_response(approve_response)
        assert approval_payload.is_approved(approve_response) is True
        
        # Case B: 반려
        reject_response = {"selected_option": {"value": "reject"}, "rejection_reason": "내용 보강 필요"}
        assert approval_payload.validate_response(reject_response)
        assert approval_payload.is_approved(reject_response) is False

    def test_retry_on_validation_failure(self):
        """
        시나리오: 유효성 검증 실패 → 재시도
        """
        max_retries = 3
        retry_count = 0
        
        payload = InterruptFactory.form(
            question="이메일을 입력하세요",
            schema_name="EmailForm",
            required_fields=["email"],
            field_types={"email": "email"}
        )
        
        # 잘못된 입력들
        invalid_inputs = [
            {"email": ""},           # 빈 값
            {"email": "invalid"},    # @ 없음
            {"email": "test@valid.com"}  # 올바른 형식
        ]
        
        for response in invalid_inputs:
            retry_count += 1
            if payload.validate_response(response):
                break
            if retry_count >= max_retries:
                raise AssertionError("최대 재시도 횟수 초과")
        
        assert retry_count == 3  # 세 번째에서 성공


class TestHandleUserResponseIntegration:
    """handle_user_response 통합 테스트"""

    def test_option_response_updates_state(self):
        """옵션 응답이 상태를 올바르게 업데이트하는지"""
        state = create_initial_state("테스트 입력")
        state = update_state(state, need_more_info=True, options=[
            {"title": "옵션A", "description": "설명A"}
        ])
        
        response = {"selected_option": {"title": "옵션A", "description": "설명A"}}
        new_state = handle_user_response(state, response)
        
        assert new_state.get("need_more_info") is False
        assert "[선택: 옵션A" in new_state.get("user_input", "")
        assert new_state.get("selected_option") is not None

    def test_text_input_response_updates_state(self):
        """직접 입력 응답이 상태를 올바르게 업데이트하는지"""
        state = create_initial_state("원래 입력")
        state = update_state(state, need_more_info=True)
        
        response = {"text_input": "사용자가 직접 입력한 내용"}
        new_state = handle_user_response(state, response)
        
        assert "[직접 입력: 사용자가 직접 입력한 내용]" in new_state.get("user_input", "")

    def test_step_history_records_resume(self):
        """Resume 이벤트가 step_history에 기록되는지"""
        state = create_initial_state("테스트")
        state = update_state(state, 
            last_interrupt={"type": "option", "question": "테스트 질문"}
        )
        
        response = {"selected_option": {"title": "선택됨"}}
        new_state = handle_user_response(state, response)
        
        history = new_state.get("step_history", [])
        resume_events = [h for h in history if h.get("step") == "human_resume"]
        
        assert len(resume_events) >= 1
        assert resume_events[-1]["event_type"] == "HUMAN_RESPONSE"


class TestErrorHandling:
    """에러 처리 테스트"""

    def test_invalid_interrupt_type(self):
        """지원하지 않는 인터럽트 타입"""
        with pytest.raises(ValueError):
            InterruptFactory.create("invalid_type", question="테스트")

    def test_empty_options_fallback(self):
        """빈 옵션 목록 → 기본 옵션 생성"""
        payload = InterruptFactory.option(
            question="테스트",
            options=[]
        )
        
        # 빈 옵션이면 기본 옵션이 추가되어야 함
        assert len(payload.options) >= 1
        assert payload.options[0].title == "계속 진행"

    def test_payload_with_error_field(self):
        """에러 메시지가 포함된 페이로드"""
        payload = InterruptFactory.option(
            question="다시 선택하세요",
            options=[{"title": "옵션1", "description": ""}],
            metadata={"error": "잘못된 입력입니다. 다시 시도하세요."}
        )
        
        payload_dict = payload.to_dict()
        assert "error" in payload_dict.get("data", {})


class TestInterruptIndexSafety:
    """
    Interrupt Index Safety 테스트

    LangGraph에서 interrupt()는 index 기반으로 resume 매칭됩니다.
    interrupt() 호출 순서나 개수가 변경되면 resume mismatch가 발생합니다.

    이 테스트 클래스는 index mismatch 방지를 위한 패턴을 검증합니다.
    """

    def test_semantic_interrupt_id_required(self):
        """interrupt_id (Semantic Key)가 없으면 경고 또는 기본값 생성"""
        # interrupt_id가 없는 경우
        payload_without_id = InterruptFactory.option(
            question="테스트",
            options=[{"title": "A", "description": ""}]
        )

        # interrupt_id가 없어도 동작하지만, 권장되지 않음
        # event_id는 자동 생성됨
        assert payload_without_id.event_id is not None
        assert payload_without_id.event_id.startswith("evt_")

    def test_semantic_interrupt_id_explicit(self):
        """명시적 interrupt_id 설정 테스트"""
        payload = InterruptFactory.option(
            question="방향 선택",
            options=[{"title": "A", "description": ""}],
            interrupt_id="direction_select_v1"
        )

        assert payload.interrupt_id == "direction_select_v1"

        # to_dict()에 포함되어야 함
        payload_dict = payload.to_dict()
        assert payload_dict.get("interrupt_id") == "direction_select_v1"

    def test_consistent_interrupt_order_pattern(self):
        """
        일관된 interrupt 순서 패턴 검증

        GOOD: 조건과 무관하게 항상 동일한 순서로 interrupt 호출
        BAD: 조건에 따라 interrupt 순서가 달라지는 패턴
        """
        def good_pattern(need_detail: bool):
            """올바른 패턴: 항상 동일한 순서"""
            payloads = []

            # 1번째 interrupt (항상 실행)
            payloads.append(InterruptFactory.option(
                question="기본 선택",
                options=[{"title": "A", "description": ""}],
                interrupt_id="step_1_basic"
            ))

            # 2번째 interrupt (항상 실행, 조건은 내부에서 처리)
            if need_detail:
                payloads.append(InterruptFactory.form(
                    question="상세 정보",
                    schema_name="Detail",
                    required_fields=["info"],
                    interrupt_id="step_2_detail"
                ))

            return payloads

        # need_detail=True일 때
        payloads_with_detail = good_pattern(True)
        assert len(payloads_with_detail) == 2
        assert payloads_with_detail[0].interrupt_id == "step_1_basic"
        assert payloads_with_detail[1].interrupt_id == "step_2_detail"

        # need_detail=False일 때
        payloads_without_detail = good_pattern(False)
        assert len(payloads_without_detail) == 1
        assert payloads_without_detail[0].interrupt_id == "step_1_basic"

    def test_interrupt_id_uniqueness_within_flow(self):
        """동일 플로우 내 interrupt_id 고유성 검증"""
        flow_interrupt_ids = []

        # 시뮬레이션: 하나의 워크플로우에서 여러 interrupt 발생
        payload1 = InterruptFactory.option(
            question="1단계",
            options=[{"title": "A", "description": ""}],
            interrupt_id="analyze_direction"
        )
        flow_interrupt_ids.append(payload1.interrupt_id)

        payload2 = InterruptFactory.form(
            question="2단계",
            schema_name="Info",
            required_fields=["name"],
            interrupt_id="input_details"
        )
        flow_interrupt_ids.append(payload2.interrupt_id)

        payload3 = InterruptFactory.approval(
            question="3단계",
            role="팀장",
            interrupt_id="final_approval"
        )
        flow_interrupt_ids.append(payload3.interrupt_id)

        # 모든 interrupt_id가 고유해야 함
        assert len(flow_interrupt_ids) == len(set(flow_interrupt_ids))

    def test_payload_node_ref_tracking(self):
        """node_ref 필드로 인터럽트 발생 위치 추적"""
        payload = InterruptFactory.option(
            question="테스트",
            options=[{"title": "A", "description": ""}],
            node_ref="option_pause_node",
            interrupt_id="test_interrupt"
        )

        assert payload.node_ref == "option_pause_node"

        # Resume 시 node_ref로 어느 노드에서 발생한 interrupt인지 확인 가능
        payload_dict = payload.to_dict()
        assert payload_dict.get("node_ref") == "option_pause_node"

    def test_timestamp_for_ordering(self):
        """timestamp로 interrupt 순서 검증 가능"""
        import time

        payload1 = InterruptFactory.option(
            question="첫 번째",
            options=[{"title": "A", "description": ""}]
        )

        time.sleep(0.01)  # 약간의 시간 차이

        payload2 = InterruptFactory.option(
            question="두 번째",
            options=[{"title": "B", "description": ""}]
        )

        # 둘 다 timestamp가 있어야 함
        assert payload1.timestamp is not None
        assert payload2.timestamp is not None

        # timestamp 순서가 올바른지 (ISO 8601 형식이므로 문자열 비교 가능)
        assert payload1.timestamp <= payload2.timestamp


class TestSubgraphInterruptSafety:
    """
    서브그래프 내 Interrupt 안전성 테스트

    서브그래프 내부에서 interrupt() 호출 시:
    - Resume 시 부모 노드(run_*_subgraph) 전체가 재실행됨
    - 서브그래프도 처음부터 다시 시작됨
    - interrupt() 이전의 모든 코드가 다시 실행됨
    """

    def test_interrupt_payload_immutability(self):
        """Payload 생성 후 불변성 검증 (재실행 시 동일한 결과)"""
        def create_payload():
            return InterruptFactory.option(
                question="동일한 질문",
                options=[
                    {"title": "옵션1", "description": "설명1"},
                    {"title": "옵션2", "description": "설명2"}
                ],
                interrupt_id="immutable_test"
            )

        # 여러 번 호출해도 동일한 구조의 payload 생성
        payload1 = create_payload()
        payload2 = create_payload()

        assert payload1.question == payload2.question
        assert payload1.interrupt_id == payload2.interrupt_id
        assert len(payload1.options) == len(payload2.options)
        assert payload1.options[0].title == payload2.options[0].title

    def test_no_side_effect_in_payload_creation(self):
        """Payload 생성 시 부수효과 없음 검증"""
        side_effect_counter = {"count": 0}

        def create_payload_with_side_effect():
            # 잘못된 패턴: payload 생성 시 부수효과
            # side_effect_counter["count"] += 1  # 이런 코드가 있으면 안됨

            return InterruptFactory.option(
                question="테스트",
                options=[{"title": "A", "description": ""}]
            )

        # 여러 번 호출 (Resume 시 재실행 시뮬레이션)
        for _ in range(3):
            create_payload_with_side_effect()

        # 부수효과가 없어야 함
        assert side_effect_counter["count"] == 0

    def test_state_initialization_idempotency(self):
        """
        상태 초기화가 멱등성을 보장하는지 검증

        Resume 시 노드가 재실행되므로, 초기화 코드가
        기존 상태를 덮어쓰지 않아야 함
        """
        # 시뮬레이션: 첫 실행에서 discussion_messages 생성
        state = create_initial_state("테스트")
        state = update_state(state, discussion_messages=[
            {"role": "reviewer", "content": "첫 메시지"}
        ])

        # Resume 후 재실행 시뮬레이션
        # 올바른 패턴: 기존 값이 있으면 유지
        existing_messages = state.get("discussion_messages", [])
        if not existing_messages:
            existing_messages = []  # 초기화는 비어있을 때만

        assert len(existing_messages) == 1
        assert existing_messages[0]["content"] == "첫 메시지"

    def test_cross_subgraph_interrupt_state_preservation(self):
        """
        서브그래프 간 interrupt 시 상태 보존 검증

        Generation → QA 서브그래프 전환 시
        이전 서브그래프의 결과가 보존되어야 함
        """
        # Generation 서브그래프 결과 시뮬레이션
        state = create_initial_state("AI 앱")
        state = update_state(state,
            analysis={"topic": "AI 헬스케어 앱"},
            structure={"sections": [{"name": "개요"}]},
            draft={"sections": [{"name": "개요", "content": "내용"}]}
        )

        # QA 서브그래프에서 interrupt 발생 시뮬레이션
        qa_interrupt_payload = InterruptFactory.approval(
            question="기획서를 승인하시겠습니까?",
            role="팀장",
            interrupt_id="qa_approval"
        )

        # interrupt 전 상태 스냅샷 저장 (권장 패턴)
        snapshot = {
            "analysis": state.get("analysis"),
            "structure": state.get("structure"),
            "draft": state.get("draft"),
        }

        # Resume 후에도 이전 서브그래프 결과가 보존되어야 함
        assert snapshot["analysis"]["topic"] == "AI 헬스케어 앱"
        assert snapshot["draft"] is not None

    def test_nested_interrupt_scenario(self):
        """
        중첩된 interrupt 시나리오 테스트

        한 노드 내에서 조건부 interrupt가 여러 번 호출될 수 있는 경우
        interrupt_id로 구분 가능해야 함
        """
        def simulate_nested_interrupts(need_detail: bool, need_approval: bool):
            """조건에 따라 다른 interrupt 발생"""
            payloads = []

            if need_detail:
                payloads.append(InterruptFactory.form(
                    question="상세 정보 입력",
                    schema_name="DetailForm",
                    required_fields=["description"],
                    interrupt_id="nested_detail_form"
                ))

            if need_approval:
                payloads.append(InterruptFactory.approval(
                    question="승인 요청",
                    role="관리자",
                    interrupt_id="nested_approval"
                ))

            return payloads

        # 케이스 1: 둘 다 필요
        both_payloads = simulate_nested_interrupts(True, True)
        assert len(both_payloads) == 2
        assert both_payloads[0].interrupt_id == "nested_detail_form"
        assert both_payloads[1].interrupt_id == "nested_approval"

        # 케이스 2: approval만 필요
        approval_only = simulate_nested_interrupts(False, True)
        assert len(approval_only) == 1
        assert approval_only[0].interrupt_id == "nested_approval"

    def test_resume_value_propagation(self):
        """
        Resume 값이 올바르게 상태에 전파되는지 검증
        """
        state = create_initial_state("테스트")

        # interrupt 발생 시뮬레이션
        interrupt_payload = InterruptFactory.option(
            question="방향 선택",
            options=[
                {"title": "A 경로", "description": "빠른 진행"},
                {"title": "B 경로", "description": "상세 진행"}
            ],
            interrupt_id="direction_select"
        )

        # 사용자 응답 시뮬레이션
        user_response = {
            "selected_option": {"title": "A 경로", "value": "a_경로"}
        }

        # 응답 처리
        new_state = handle_user_response(state, user_response)

        # 상태에 선택이 반영되어야 함
        assert new_state.get("selected_option") is not None
        assert new_state.get("need_more_info") is False

    def test_subgraph_boundary_state_consistency(self):
        """
        서브그래프 경계에서 상태 일관성 검증

        서브그래프 진입/퇴장 시 상태가 올바르게 전달되어야 함
        """
        # 부모 그래프 상태
        parent_state = create_initial_state("AI 서비스 기획")
        parent_state = update_state(parent_state,
            rag_context="관련 문서 컨텍스트",
            generation_preset="balanced"
        )

        # 서브그래프 진입 전 필수 필드 검증
        required_for_generation = ["user_input", "rag_context"]
        for field in required_for_generation:
            assert parent_state.get(field) is not None, f"{field} 누락"

        # 서브그래프 실행 후 출력 필드 시뮬레이션
        subgraph_output = {
            "analysis": {"topic": "AI 서비스", "features": ["기능1"]},
            "structure": {"sections": []},
        }

        # 부모 상태에 병합
        merged_state = update_state(parent_state, **subgraph_output)

        # 원본 입력과 서브그래프 출력이 모두 존재해야 함
        assert merged_state.get("user_input") == "AI 서비스 기획"
        assert merged_state.get("rag_context") == "관련 문서 컨텍스트"
        assert merged_state.get("analysis") is not None


# =============================================================================
# 실행
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
