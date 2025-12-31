"""
인터럽트 타입 시스템 테스트

graph/interrupt_types.py 모듈의 단위 테스트입니다.
"""

import pytest
from graph.interrupt_types import (
    InterruptType,
    InterruptFactory,
    ResumeHandler,
    BaseInterruptPayload,
    OptionInterruptPayload,
    FormInterruptPayload,
    ConfirmInterruptPayload,
    ApprovalInterruptPayload,
    InterruptOption,
    normalize_options,  # [NEW]
)


# =============================================================================
# InterruptType Enum 테스트
# =============================================================================

class TestInterruptType:
    """InterruptType Enum 테스트"""

    def test_enum_values(self):
        """Enum 값들이 올바른지 확인"""
        assert InterruptType.OPTION.value == "option"
        assert InterruptType.FORM.value == "form"
        assert InterruptType.CONFIRM.value == "confirm"
        assert InterruptType.APPROVAL.value == "approval"

    def test_string_conversion(self):
        """Enum이 문자열로 변환되는지 확인"""
        assert str(InterruptType.OPTION) == "InterruptType.OPTION"
        assert InterruptType.OPTION == "option"  # str 상속으로 비교 가능


# =============================================================================
# OptionInterruptPayload 테스트
# =============================================================================

class TestOptionInterruptPayload:
    """옵션 인터럽트 페이로드 테스트"""

    def test_create_basic(self):
        """기본 옵션 페이로드 생성"""
        payload = OptionInterruptPayload(
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")]
        )
        assert payload.type == InterruptType.OPTION
        assert payload.question == "선택하세요"
        assert len(payload.options) == 1

    def test_empty_options_fallback(self):
        """빈 옵션 시 기본값 생성"""
        payload = OptionInterruptPayload(question="선택하세요", options=[])
        assert len(payload.options) == 1
        assert payload.options[0].title == "계속 진행"

    def test_to_dict(self):
        """딕셔너리 변환 확인"""
        payload = OptionInterruptPayload(
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")]
        )
        result = payload.to_dict()
        assert result["type"] == "option"
        assert result["question"] == "선택하세요"
        assert isinstance(result["options"], list)

    def test_validate_response_with_selected(self):
        """선택된 옵션 응답 검증"""
        payload = OptionInterruptPayload(
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")]
        )
        assert payload.validate_response({"selected_option": {"title": "A"}})

    def test_validate_response_with_text(self):
        """직접 입력 응답 검증"""
        payload = OptionInterruptPayload(
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")],
            allow_custom=True
        )
        assert payload.validate_response({"text_input": "직접 입력"})

    def test_validate_response_empty(self):
        """빈 응답 검증 실패"""
        payload = OptionInterruptPayload(
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")]
        )
        assert not payload.validate_response({})


# =============================================================================
# FormInterruptPayload 테스트
# =============================================================================

class TestFormInterruptPayload:
    """폼 인터럽트 페이로드 테스트"""

    def test_create_basic(self):
        """기본 폼 페이로드 생성"""
        payload = FormInterruptPayload(
            question="정보를 입력하세요",
            input_schema_name="UserInputSchema",
            required_fields=["name", "email"]
        )
        assert payload.type == InterruptType.FORM
        assert payload.input_schema_name == "UserInputSchema"

    def test_validate_response_with_required_fields(self):
        """필수 필드 포함 응답 검증"""
        payload = FormInterruptPayload(
            question="정보를 입력하세요",
            input_schema_name="UserInputSchema",
            required_fields=["name", "email"]
        )
        assert payload.validate_response({"name": "홍길동", "email": "test@test.com"})

    def test_validate_response_missing_required(self):
        """필수 필드 누락 응답 검증 실패"""
        payload = FormInterruptPayload(
            question="정보를 입력하세요",
            input_schema_name="UserInputSchema",
            required_fields=["name", "email"]
        )
        assert not payload.validate_response({"name": "홍길동"})


# =============================================================================
# ConfirmInterruptPayload 테스트
# =============================================================================

class TestConfirmInterruptPayload:
    """확인 인터럽트 페이로드 테스트"""

    def test_create_basic(self):
        """기본 확인 페이로드 생성"""
        payload = ConfirmInterruptPayload(question="진행하시겠습니까?")
        assert payload.type == InterruptType.CONFIRM
        assert payload.confirm_text == "예"
        assert payload.cancel_text == "아니오"

    def test_validate_response_confirmed(self):
        """확인 응답 검증"""
        payload = ConfirmInterruptPayload(question="진행하시겠습니까?")
        assert payload.validate_response({"confirmed": True})
        assert payload.validate_response({"confirmed": False})

    def test_validate_response_missing(self):
        """확인 값 누락 검증 실패"""
        payload = ConfirmInterruptPayload(question="진행하시겠습니까?")
        assert not payload.validate_response({})


# =============================================================================
# ApprovalInterruptPayload 테스트
# =============================================================================

class TestApprovalInterruptPayload:
    """승인 인터럽트 페이로드 테스트"""

    def test_create_basic(self):
        """기본 승인 페이로드 생성"""
        payload = ApprovalInterruptPayload(
            question="승인하시겠습니까?",
            role="팀장"
        )
        assert payload.type == InterruptType.APPROVAL
        assert payload.role == "팀장"
        assert len(payload.options) == 2

    def test_is_approved_true(self):
        """승인 판정 확인"""
        payload = ApprovalInterruptPayload(question="승인?", role="팀장")
        assert payload.is_approved({"approved": True})
        assert payload.is_approved({"selected_option": {"value": "approve"}})

    def test_is_approved_false(self):
        """반려 판정 확인"""
        payload = ApprovalInterruptPayload(question="승인?", role="팀장")
        assert not payload.is_approved({"approved": False})
        assert not payload.is_approved({"selected_option": {"value": "reject"}})


# =============================================================================
# InterruptFactory 테스트
# =============================================================================

class TestInterruptFactory:
    """인터럽트 팩토리 테스트"""

    def test_create_option(self):
        """옵션 타입 생성"""
        payload = InterruptFactory.create(
            InterruptType.OPTION,
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")]
        )
        assert isinstance(payload, OptionInterruptPayload)

    def test_create_from_string(self):
        """문자열로 타입 생성"""
        payload = InterruptFactory.create(
            "option",
            question="선택하세요",
            options=[InterruptOption(title="A", description="옵션 A")]
        )
        assert isinstance(payload, OptionInterruptPayload)

    def test_create_form(self):
        """폼 타입 생성"""
        payload = InterruptFactory.create(
            InterruptType.FORM,
            question="입력하세요",
            input_schema_name="TestSchema"
        )
        assert isinstance(payload, FormInterruptPayload)

    def test_create_confirm(self):
        """확인 타입 생성"""
        payload = InterruptFactory.create(
            InterruptType.CONFIRM,
            question="진행하시겠습니까?"
        )
        assert isinstance(payload, ConfirmInterruptPayload)

    def test_create_approval(self):
        """승인 타입 생성"""
        payload = InterruptFactory.create(
            InterruptType.APPROVAL,
            question="승인하시겠습니까?",
            role="팀장"
        )
        assert isinstance(payload, ApprovalInterruptPayload)

    def test_create_invalid_type(self):
        """잘못된 타입 예외 발생"""
        with pytest.raises(ValueError):
            InterruptFactory.create("invalid_type", question="테스트")


# =============================================================================
# ResumeHandler 테스트
# =============================================================================

class TestResumeHandler:
    """응답 핸들러 테스트"""

    def test_handle_option(self):
        """옵션 응답 처리"""
        result = ResumeHandler.handle(
            InterruptType.OPTION,
            {"selected_option": {"title": "A"}}
        )
        assert result["action"] == "option_selected"
        assert result["selected_option"]["title"] == "A"

    def test_handle_confirm(self):
        """확인 응답 처리"""
        result = ResumeHandler.handle(
            InterruptType.CONFIRM,
            {"confirmed": True}
        )
        assert result["action"] == "confirmed"
        assert result["confirmed"] is True

    def test_handle_approval_approved(self):
        """승인 응답 처리"""
        result = ResumeHandler.handle(
            InterruptType.APPROVAL,
            {"selected_option": {"value": "approve"}}
        )
        assert result["action"] == "approved"
        assert result["approved"] is True

    def test_handle_approval_rejected(self):
        """반려 응답 처리"""
        result = ResumeHandler.handle(
            InterruptType.APPROVAL,
            {"selected_option": {"value": "reject"}, "rejection_reason": "수정 필요"}
        )
        assert result["action"] == "rejected"
        assert result["approved"] is False
        assert result["rejection_reason"] == "수정 필요"


# =============================================================================
# 통합 테스트
# =============================================================================

class TestIntegration:
    """통합 테스트"""

    def test_full_option_flow(self):
        """옵션 인터럽트 전체 흐름"""
        # 1. 페이로드 생성
        payload = InterruptFactory.create(
            InterruptType.OPTION,
            question="방향을 선택하세요",
            options=[
                InterruptOption(title="A", description="방향 A"),
                InterruptOption(title="B", description="방향 B"),
            ]
        )

        # 2. 딕셔너리로 변환 (interrupt() 전달용)
        payload_dict = payload.to_dict()
        assert payload_dict["type"] == "option"

        # 3. 사용자 응답 시뮬레이션
        user_response = {"selected_option": {"title": "A", "description": "방향 A"}}

        # 4. 응답 검증
        assert payload.validate_response(user_response)

        # 5. 응답 처리
        result = ResumeHandler.handle(InterruptType.OPTION, user_response)
        assert result["selected_option"]["title"] == "A"

    def test_full_approval_flow(self):
        """승인 인터럽트 전체 흐름"""
        # 1. 페이로드 생성
        payload = InterruptFactory.create(
            InterruptType.APPROVAL,
            question="이 기획서를 승인하시겠습니까?",
            role="팀장"
        )

        # 2. 딕셔너리로 변환
        payload_dict = payload.to_dict()
        assert payload_dict["role"] == "팀장"

        # 3. 승인 응답 시뮬레이션
        approve_response = {"selected_option": {"value": "approve"}}
        assert payload.validate_response(approve_response)
        assert payload.is_approved(approve_response)

        # 4. 반려 응답 시뮬레이션
        reject_response = {"selected_option": {"value": "reject"}, "rejection_reason": "근거 부족"}
        assert payload.validate_response(reject_response)
        assert not payload.is_approved(reject_response)


# =============================================================================
# [NEW] InterruptOption.from_any 테스트
# =============================================================================

class TestInterruptOptionFromAny:
    """InterruptOption.from_any 변환 테스트"""

    def test_from_dict(self):
        """딕셔너리에서 변환"""
        opt = InterruptOption.from_any({"title": "A", "description": "설명A"})
        assert opt.title == "A"
        assert opt.description == "설명A"

    def test_from_dict_with_value(self):
        """value 포함 딕셔너리에서 변환"""
        opt = InterruptOption.from_any({"title": "A", "description": "설명", "value": "opt_a"})
        assert opt.value == "opt_a"

    def test_from_interrupt_option(self):
        """InterruptOption 인스턴스는 그대로 반환"""
        original = InterruptOption(title="A", description="설명")
        result = InterruptOption.from_any(original)
        assert result is original

    def test_from_duck_typing_object(self):
        """duck-typing 객체에서 변환 (title, description 속성 보유)"""
        class FakeOption:
            title = "Fake"
            description = "Duck typing"

        opt = InterruptOption.from_any(FakeOption())
        assert opt.title == "Fake"
        assert opt.description == "Duck typing"

    def test_from_invalid_raises(self):
        """변환 불가능한 타입은 ValueError 발생"""
        with pytest.raises(ValueError):
            InterruptOption.from_any(12345)

        with pytest.raises(ValueError):
            InterruptOption.from_any(None)


# =============================================================================
# [NEW] normalize_options 테스트
# =============================================================================

class TestNormalizeOptions:
    """옵션 정규화 유틸리티 테스트"""

    def test_normalize_dict_list(self):
        """딕셔너리 리스트 정규화"""
        options = normalize_options([
            {"title": "A", "description": "옵션A"},
            {"title": "B", "description": "옵션B"},
        ])
        assert len(options) == 2
        assert all(isinstance(o, InterruptOption) for o in options)
        assert options[0].title == "A"

    def test_normalize_mixed_list(self):
        """혼합된 형태 리스트 정규화"""
        options = normalize_options([
            {"title": "Dict", "description": "딕셔너리"},
            InterruptOption(title="Model", description="모델"),
        ])
        assert len(options) == 2
        assert options[0].title == "Dict"
        assert options[1].title == "Model"

    def test_normalize_empty_list(self):
        """빈 리스트 정규화"""
        options = normalize_options([])
        assert options == []

    def test_normalize_invalid_fallback(self):
        """변환 불가 항목은 문자열로 대체"""
        options = normalize_options([123, "문자열"])
        assert len(options) == 2
        assert options[0].title == "123"
        assert options[1].title == "문자열"


# =============================================================================
# [NEW] FormInterruptPayload 타입 검증 테스트
# =============================================================================

class TestFormValidationErrors:
    """폼 타입 검증 에러 테스트"""

    def test_get_validation_errors_missing_required(self):
        """필수 필드 누락 에러"""
        payload = FormInterruptPayload(
            question="입력하세요",
            input_schema_name="TestSchema",
            required_fields=["name", "email"]
        )
        errors = payload.get_validation_errors({"name": "홍길동"})
        assert len(errors) == 1
        assert "email" in errors[0]

    def test_get_validation_errors_empty_required(self):
        """필수 필드 비어있음 에러"""
        payload = FormInterruptPayload(
            question="입력하세요",
            input_schema_name="TestSchema",
            required_fields=["name"]
        )
        errors = payload.get_validation_errors({"name": ""})
        assert len(errors) == 1
        assert "비어있음" in errors[0]

    def test_get_validation_errors_type_mismatch(self):
        """타입 불일치 에러"""
        payload = FormInterruptPayload(
            question="입력하세요",
            input_schema_name="TestSchema",
            required_fields=["age"],
            field_types={"age": "int"}
        )
        errors = payload.get_validation_errors({"age": "not_a_number"})
        assert len(errors) == 1
        assert "타입 불일치" in errors[0]

    def test_get_validation_errors_valid_types(self):
        """유효한 타입 검증 통과"""
        payload = FormInterruptPayload(
            question="입력하세요",
            input_schema_name="TestSchema",
            required_fields=["name", "age", "email"],
            field_types={"name": "str", "age": "int", "email": "email"}
        )
        errors = payload.get_validation_errors({
            "name": "홍길동",
            "age": 25,
            "email": "test@example.com"
        })
        assert len(errors) == 0

    def test_string_number_as_int(self):
        """문자열 숫자도 int로 인정"""
        payload = FormInterruptPayload(
            question="입력하세요",
            input_schema_name="TestSchema",
            field_types={"age": "int"}
        )
        errors = payload.get_validation_errors({"age": "25"})
        assert len(errors) == 0


# =============================================================================
# [NEW] 다중 인터럽트 시나리오 테스트
# =============================================================================

class TestMultiInterruptScenarios:
    """다중 인터럽트 시나리오 테스트"""

    def test_option_then_confirm_flow(self):
        """옵션 선택 후 확인 인터럽트 시나리오"""
        # 1단계: 옵션 선택
        option_payload = InterruptFactory.create(
            InterruptType.OPTION,
            question="카테고리를 선택하세요",
            options=[
                InterruptOption(title="IT", description="IT 서비스"),
                InterruptOption(title="F&B", description="외식 서비스"),
            ]
        )

        option_response = {"selected_option": {"title": "IT", "description": "IT 서비스"}}
        assert option_payload.validate_response(option_response)

        # 2단계: 확인
        confirm_payload = InterruptFactory.create(
            InterruptType.CONFIRM,
            question="IT 카테고리로 진행하시겠습니까?"
        )

        confirm_response = {"confirmed": True}
        assert confirm_payload.validate_response(confirm_response)

    def test_form_then_approval_flow(self):
        """폼 입력 후 승인 인터럽트 시나리오"""
        # 1단계: 폼 입력
        form_payload = InterruptFactory.create(
            InterruptType.FORM,
            question="추가 정보를 입력하세요",
            input_schema_name="AdditionalInfo",
            required_fields=["target_user", "budget"]
        )

        form_response = {"target_user": "20대 직장인", "budget": "1000만원"}
        assert form_payload.validate_response(form_response)

        # 2단계: 승인
        approval_payload = InterruptFactory.create(
            InterruptType.APPROVAL,
            question="이 정보로 기획서를 생성하시겠습니까?",
            role="기획자"
        )

        approval_response = {"selected_option": {"value": "approve"}}
        assert approval_payload.validate_response(approval_response)
        assert approval_payload.is_approved(approval_response)

    def test_approval_rejection_with_feedback(self):
        """승인 반려 시 피드백 포함 시나리오"""
        payload = InterruptFactory.create(
            InterruptType.APPROVAL,
            question="기획서를 검토해주세요",
            role="팀장"
        )

        reject_response = {
            "selected_option": {"value": "reject"},
            "rejection_reason": "예산 부분 재검토 필요"
        }

        assert payload.validate_response(reject_response)
        assert not payload.is_approved(reject_response)

        # ResumeHandler로 처리
        result = ResumeHandler.handle(InterruptType.APPROVAL, reject_response)
        assert result["action"] == "rejected"
        assert result["rejection_reason"] == "예산 부분 재검토 필요"

    def test_complex_option_with_custom_input(self):
        """옵션 + 직접 입력 복합 시나리오"""
        payload = InterruptFactory.create(
            InterruptType.OPTION,
            question="서비스 방향을 선택하세요",
            options=[
                InterruptOption(title="AI 헬스케어", description="AI 기반 건강관리"),
                InterruptOption(title="핀테크", description="금융 서비스"),
            ],
            allow_custom=True
        )

        # 옵션 선택
        assert payload.validate_response({"selected_option": {"title": "AI 헬스케어"}})

        # 직접 입력
        assert payload.validate_response({"text_input": "AI 교육 플랫폼"})
