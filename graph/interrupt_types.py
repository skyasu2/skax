"""
Human Interrupt Types - 모듈화된 인터럽트 타입 시스템

LangGraph HITL 패턴을 위한 타입 안전한 인터럽트 페이로드 관리 모듈입니다.

설계 원칙:
    - 각 인터럽트 타입별 독립적인 Payload 클래스
    - 공통 인터페이스(BaseInterruptPayload) 상속으로 일관된 API
    - InterruptFactory를 통한 타입별 인스턴스 생성
    - Pydantic 기반 유효성 검증

지원 인터럽트 타입:
    - OPTION: 옵션 선택 (단일/다중)
    - FORM: 동적 폼 입력
    - CONFIRM: 예/아니오 확인
    - APPROVAL: 역할 기반 승인 (승인/반려)

=============================================================================
표준 Payload 필드 레퍼런스 (Canonical Field Reference)
=============================================================================

┌─────────────────┬─────────────┬───────────────────────────────────────────┐
│ 필드            │ 필수 여부   │ 설명                                       │
├─────────────────┼─────────────┼───────────────────────────────────────────┤
│ type            │ ✅ 필수     │ 인터럽트 유형 (option/form/confirm/approval)│
│ question        │ ✅ 필수     │ 사용자에게 표시할 질문                     │
│ data            │ ⬜ 선택     │ 추가 메타데이터 (컨텍스트 정보)            │
├─────────────────┼─────────────┼───────────────────────────────────────────┤
│ [추적 필드]     │             │                                           │
│ node_ref        │ ⬜ 권장     │ 인터럽트 발생 노드 이름                    │
│ event_id        │ ⬜ 권장     │ 이벤트 추적 ID (UUID)                      │
│ timestamp       │ ⬜ 자동     │ 인터럽트 발생 시각 (ISO 8601)              │
├─────────────────┼─────────────┼───────────────────────────────────────────┤
│ [안전성 필드]   │             │                                           │
│ interrupt_id    │ ⬜ 권장     │ Semantic Key (Resume Mismatch 방지)        │
│ expires_at      │ ⬜ 선택     │ 인터럽트 만료 시각 (타임아웃 처리)         │
├─────────────────┼─────────────┼───────────────────────────────────────────┤
│ [디버깅 필드]   │             │                                           │
│ snapshot        │ ⬜ 선택     │ 직전 상태 스냅샷 (Time-Travel 지원)        │
│ hint            │ ⬜ 선택     │ 사용자 가이드 힌트 (재시도 안내)           │
└─────────────────┴─────────────┴───────────────────────────────────────────┘

모든 필드는 BaseInterruptPayload에서 정의되어 일원화 관리됩니다.
개별 Payload 클래스(OptionInterruptPayload 등)에서 중복 정의하지 마세요.

=============================================================================

사용 예시:
    from graph.interrupt_types import InterruptFactory, InterruptType, InterruptOption

    # ─────────────────────────────────────────────────────────────
    # 예시 1: 옵션 선택 인터럽트
    # ─────────────────────────────────────────────────────────────
    payload = InterruptFactory.create(
        InterruptType.OPTION,
        question="다음 단계를 선택하세요",
        options=[
            InterruptOption(title="기획서 작성", description="AI가 초안을 작성합니다"),
            InterruptOption(title="추가 분석", description="자료를 더 수집합니다"),
        ],
        allow_custom=True,  # 직접 입력 허용
        node_ref="option_pause",  # 발생 노드 (추적용)
        interrupt_id="direction_select"  # Semantic Key (Resume 매칭)
    )
    user_response = interrupt(payload.to_dict())
    # user_response 예시: {"selected_option": {"title": "기획서 작성", ...}}

    # ─────────────────────────────────────────────────────────────
    # 예시 2: 역할 기반 승인 인터럽트
    # ─────────────────────────────────────────────────────────────
    approval_payload = InterruptFactory.create(
        InterruptType.APPROVAL,
        question="기획서 초안을 검토해주세요",
        role="팀장",
        rejection_feedback_enabled=True
    )
    # user_response 예시: {"approved": True} 또는 {"approved": False, "feedback": "수정 필요"}

    # ─────────────────────────────────────────────────────────────
    # 예시 3: 동적 폼 인터럽트
    # ─────────────────────────────────────────────────────────────
    form_payload = InterruptFactory.create(
        InterruptType.FORM,
        question="상세 정보를 입력해주세요",
        input_schema_name="UserInfo",
        required_fields=["email", "company"],
        field_types={"email": "email", "company": "str"}
    )
    # user_response 예시: {"email": "user@example.com", "company": "Acme Inc"}

    # ─────────────────────────────────────────────────────────────
    # 예시 4: 간단한 확인 인터럽트
    # ─────────────────────────────────────────────────────────────
    confirm_payload = InterruptFactory.create(
        InterruptType.CONFIRM,
        question="이대로 진행하시겠습니까?",
        confirm_text="예, 진행합니다",
        cancel_text="아니오, 취소합니다"
    )
    # user_response 예시: {"confirmed": True}
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Union, Type
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing_extensions import Self


# =============================================================================
# Validation Mode & Exceptions (개선 1: Strict Validation)
# =============================================================================

class ValidationMode(str, Enum):
    """
    검증 모드 설정

    STRICT: 검증 실패 시 ValueError 발생 (운영 환경 권장)
    LENIENT: 검증 실패 시 경고 출력 후 기본값 사용 (개발/테스트용)
    """
    STRICT = "strict"
    LENIENT = "lenient"


# 전역 검증 모드 설정 (환경변수 또는 설정에서 변경 가능)
import os
_VALIDATION_MODE = ValidationMode(os.getenv("HITL_VALIDATION_MODE", "strict"))


def set_validation_mode(mode: ValidationMode):
    """검증 모드 설정"""
    global _VALIDATION_MODE
    _VALIDATION_MODE = mode


def get_validation_mode() -> ValidationMode:
    """현재 검증 모드 반환"""
    return _VALIDATION_MODE


class HITLValidationError(ValueError):
    """
    HITL 검증 오류

    Strict 모드에서 검증 실패 시 발생합니다.
    graceful degradation 또는 fail-fast 처리에 사용됩니다.

    Attributes:
        field: 검증 실패한 필드명
        reason: 실패 사유
        original_value: 원본 값 (디버깅용)

    Example:
        try:
            validate_resume_value(response)
        except HITLValidationError as e:
            logger.error(f"Resume 검증 실패: {e.field} - {e.reason}")
            # graceful degradation: 기본값 사용
            # 또는 fail-fast: 에러 전파
    """
    def __init__(self, field: str, reason: str, original_value: Any = None):
        self.field = field
        self.reason = reason
        self.original_value = original_value
        super().__init__(f"[{field}] {reason}")


def validate_or_warn(field: str, reason: str, original_value: Any = None) -> None:
    """
    검증 모드에 따라 예외 발생 또는 경고 출력

    Args:
        field: 검증 실패한 필드명
        reason: 실패 사유
        original_value: 원본 값

    Raises:
        HITLValidationError: STRICT 모드에서 검증 실패 시
    """
    if _VALIDATION_MODE == ValidationMode.STRICT:
        raise HITLValidationError(field, reason, original_value)
    else:
        print(f"[WARN] HITL Validation: [{field}] {reason}")


# =============================================================================
# InterruptType Enum - 타입 안전한 인터럽트 유형 정의
# =============================================================================

class InterruptType(str, Enum):
    """
    인터럽트 유형 상수

    str 상속으로 JSON 직렬화 시 자동으로 문자열로 변환됩니다.
    """
    OPTION = "option"           # 옵션 선택 (단일/다중)
    FORM = "form"               # 동적 폼 입력
    CONFIRM = "confirm"         # 예/아니오 확인
    APPROVAL = "approval"       # 역할 기반 승인
    OPTION_SELECTOR = "option_selector"  # 기존 호환용


# =============================================================================
# Pydantic 기반 Payload 모델들
# =============================================================================

class InterruptOption(BaseModel):
    """인터럽트 옵션 항목

    파이프라인 추적을 위해 각 옵션에 고유 id를 부여합니다.
    id는 HITL 이벤트 로깅, step_history 기록, 디버깅에 활용됩니다.
    value는 프로그래밍적 식별자로, 승인 워크플로우 등에서 사용됩니다.
    """
    id: str = Field(default="", description="고유 식별자 (파이프라인 추적용)")
    title: str = Field(description="옵션 제목")
    description: str = Field(default="", description="옵션 설명")
    value: str = Field(default="", description="프로그래밍적 식별자 (예: approve, reject)")

    def __init__(self, **data):
        super().__init__(**data)
        # id가 없으면 title 기반으로 자동 생성
        if not self.id:
            import re
            # title을 snake_case로 변환하여 id 생성
            self.id = re.sub(r'[^a-zA-Z0-9가-힣]', '_', self.title).lower().strip('_')
        # value가 없으면 id와 동일하게 설정
        if not self.value:
            self.value = self.id

    @classmethod
    def from_any(cls, obj: Any) -> "InterruptOption":
        """
        다양한 형태의 입력을 InterruptOption으로 변환 (일관성 보장)

        지원 형태:
        - dict: {"title": "...", "description": "..."}
        - InterruptOption 인스턴스
        - duck-typing 객체 (title, description 속성 보유)

        Returns:
            InterruptOption 인스턴스

        Raises:
            ValueError: 변환 불가능한 형태
        """
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, dict):
            return cls(
                id=obj.get("id", ""),
                title=obj.get("title", ""),
                description=obj.get("description", ""),
            )
        if hasattr(obj, "title") and hasattr(obj, "description"):
            # Duck typing: OptionChoice 등 호환 객체
            return cls(
                id=getattr(obj, "id", ""),
                title=getattr(obj, "title", ""),
                description=getattr(obj, "description", ""),
            )
        raise ValueError(f"InterruptOption으로 변환 불가: {type(obj)}")

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (UI/직렬화용)"""
        return self.model_dump(exclude_none=True)


def normalize_options(options: List[Any]) -> List[InterruptOption]:
    """
    옵션 목록을 InterruptOption 리스트로 정규화

    다양한 형태의 옵션 목록을 일관된 InterruptOption 리스트로 변환합니다.

    Args:
        options: dict, InterruptOption, 또는 duck-typing 객체의 리스트

    Returns:
        List[InterruptOption]: 정규화된 옵션 리스트

    Raises:
        HITLValidationError: STRICT 모드에서 변환 불가 시

    Example:
        # 혼합된 형태도 처리 가능
        options = normalize_options([
            {"title": "A", "description": "설명A"},
            InterruptOption(title="B", description="설명B"),
            some_pydantic_option_choice,  # duck-typing
        ])
    """
    normalized = []
    for i, opt in enumerate(options):
        try:
            normalized.append(InterruptOption.from_any(opt))
        except ValueError as e:
            # [개선 1] Strict Validation 적용
            validate_or_warn(
                field=f"options[{i}]",
                reason=f"옵션 변환 실패: {e}",
                original_value=opt
            )
            # LENIENT 모드에서만 도달: 기본 옵션으로 대체
            normalized.append(InterruptOption(title=str(opt), description=""))
    return normalized


class BaseInterruptPayload(BaseModel, ABC):
    """
    인터럽트 페이로드 베이스 클래스

    모든 인터럽트 타입이 상속하는 추상 기반 클래스입니다.
    공통 필드와 메서드를 정의합니다.

    공통 페이로드 스키마:
        {
            "type": "option|form|confirm|approval",
            "question": "사용자에게 보여줄 질문",
            "node_ref": "option_pause",  # 인터럽트 발생 노드
            "event_id": "evt_abc123",     # 이벤트 추적 ID
            "timestamp": "2024-01-01T12:00:00",
            "data": {...}
        }
    """
    type: InterruptType = Field(description="인터럽트 유형")
    question: str = Field(description="사용자에게 보여줄 질문")
    data: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")

    # [NEW] 추적용 메타필드 (운영/디버깅/감사용)
    node_ref: Optional[str] = Field(default=None, description="인터럽트 발생 노드 이름")
    event_id: Optional[str] = Field(default=None, description="이벤트 추적 ID (UUID)")
    timestamp: Optional[str] = Field(default=None, description="인터럽트 발생 시각 (ISO 8601)")
    
    # [NEW] Semantic Key & Expiry
    interrupt_id: Optional[str] = Field(default=None, description="인터럽트 의미론적 식별자 (Semantic Key)")
    expires_at: Optional[str] = Field(default=None, description="인터럽트 만료 시각 (ISO 8601)")
    
    # [NEW] Phase 6 Enhancements
    snapshot: Optional[Dict[str, Any]] = Field(default=None, description="직전 상태 스냅샷 (디버깅용)")
    hint: Optional[str] = Field(default=None, description="사용자 가이드 힌트 (재시도 시)")

    @abstractmethod
    def validate_response(self, response: Dict[str, Any]) -> bool:
        """사용자 응답 유효성 검증 (서브클래스에서 구현)"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """interrupt() 호출용 딕셔너리 변환"""
        return self.model_dump(mode="json")

    model_config = ConfigDict(use_enum_values=True)  # Enum을 문자열로 직렬화


class OptionInterruptPayload(BaseInterruptPayload):
    """
    옵션 선택 인터럽트 페이로드

    사용자에게 옵션 목록을 제시하고 선택을 받습니다.

    JSON Example:
        {
            "type": "option",
            "question": "다음 단계 진행 방향을 선택하세요",
            "options": [
                {"title": "기획서 작성", "description": "AI가 초안을 작성합니다", "value": "write"},
                {"title": "추가 분석", "description": "자료를 더 수집합니다", "value": "analyze"}
            ],
            "allow_multiple": false,
            "allow_custom": true
        }
    """
    type: InterruptType = Field(default=InterruptType.OPTION)
    options: List[InterruptOption] = Field(default_factory=list, description="선택 가능한 옵션들")
    allow_multiple: bool = Field(default=False, description="다중 선택 허용 여부")
    allow_custom: bool = Field(default=True, description="직접 입력 허용 여부")

    @field_validator('options')
    @classmethod
    def validate_options_not_empty(cls, v: List[InterruptOption]) -> List[InterruptOption]:
        """옵션은 최소 1개 이상 필요"""
        if not v:
            return [InterruptOption(title="계속 진행", description="기본값으로 진행합니다")]
        return v

    def validate_response(self, response: Dict[str, Any]) -> bool:
        """옵션 선택 응답 검증"""
        selected = response.get("selected_option")
        text_input = response.get("text_input")

        # 옵션 선택 또는 직접 입력 중 하나는 있어야 함
        if selected or (self.allow_custom and text_input):
            return True
        return False


class FormInterruptPayload(BaseInterruptPayload):
    """
    동적 폼 입력 인터럽트 페이로드

    Pydantic 스키마 기반으로 동적 폼을 생성합니다.

    JSON Example:
        {
            "type": "form",
            "question": "상세 정보를 입력해주세요",
            "input_schema_name": "UserInfo",
            "required_fields": ["email", "age"],
            "field_types": {"email": "email", "age": "int"}
        }
    """
    type: InterruptType = Field(default=InterruptType.FORM)
    input_schema_name: str = Field(description="입력 폼 스키마 이름 (Pydantic 모델명)")
    required_fields: List[str] = Field(default_factory=list, description="필수 입력 필드 목록")
    field_types: Dict[str, str] = Field(default_factory=dict, description="필드별 타입 힌트 (검증용)")

    def validate_response(self, response: Dict[str, Any]) -> bool:
        """폼 응답 검증 - 필수 필드 존재 및 타입 검증"""
        validation_errors = self.get_validation_errors(response)
        return len(validation_errors) == 0

    def get_validation_errors(self, response: Dict[str, Any]) -> List[str]:
        """
        폼 응답 검증 에러 목록 반환 (UI 피드백용)

        Returns:
            검증 실패한 필드와 에러 메시지 목록
        """
        errors = []

        # 1. 필수 필드 존재 여부 검증
        for field in self.required_fields:
            if field not in response:
                errors.append(f"필수 필드 누락: {field}")
            elif response[field] is None or response[field] == "":
                errors.append(f"필수 필드 비어있음: {field}")

        # 2. 타입 검증 (field_types 정의된 경우)
        type_validators = {
            "str": lambda v: isinstance(v, str),
            "int": lambda v: isinstance(v, int) or (isinstance(v, str) and v.isdigit()),
            "float": lambda v: isinstance(v, (int, float)) or self._is_float_str(v),
            "bool": lambda v: isinstance(v, bool) or v in ("true", "false", "True", "False"),
            "list": lambda v: isinstance(v, list),
            "email": lambda v: isinstance(v, str) and "@" in v and "." in v,
        }

        for field, expected_type in self.field_types.items():
            if field in response and response[field] is not None:
                validator = type_validators.get(expected_type)
                if validator and not validator(response[field]):
                    errors.append(f"타입 불일치: {field} (기대: {expected_type})")

        return errors

    @staticmethod
    def _is_float_str(v: Any) -> bool:
        """문자열이 float로 변환 가능한지 확인"""
        if not isinstance(v, str):
            return False
        try:
            float(v)
            return True
        except ValueError:
            return False


class ConfirmInterruptPayload(BaseInterruptPayload):
    """
    확인(예/아니오) 인터럽트 페이로드

    단순 예/아니오 선택을 받습니다.

    JSON Example:
        {
            "type": "confirm",
            "question": "정말 삭제하시겠습니까?",
            "confirm_text": "네, 삭제합니다",
            "cancel_text": "취소",
            "default_value": false
        }
    """
    type: InterruptType = Field(default=InterruptType.CONFIRM)
    confirm_text: str = Field(default="예", description="확인 버튼 텍스트")
    cancel_text: str = Field(default="아니오", description="취소 버튼 텍스트")
    default_value: bool = Field(default=False, description="기본값")

    def validate_response(self, response: Dict[str, Any]) -> bool:
        """확인 응답 검증"""
        confirmed = response.get("confirmed")
        return confirmed is not None


class ApprovalInterruptPayload(BaseInterruptPayload):
    """
    역할 기반 승인 인터럽트 페이로드

    팀장/리더/QA 등 역할별 승인 워크플로우에 사용됩니다.

    JSON Example:
        {
            "type": "approval",
            "question": "기획서 초안 승인 요청",
            "role": "팀장",
            "options": [
                {"title": "✅ 승인", "value": "approve"},
                {"title": "🔄 반려", "value": "reject"}
            ],
            "rejection_feedback_enabled": true
        }
    """
    type: InterruptType = Field(default=InterruptType.APPROVAL)
    role: str = Field(description="승인자 역할 (예: 팀장, 리더, QA)")
    options: List[InterruptOption] = Field(
        default_factory=lambda: [
            InterruptOption(title="✅ 승인", value="approve", description="진행합니다"),
            InterruptOption(title="🔄 반려", value="reject", description="수정이 필요합니다")
        ]
    )
    rejection_feedback_enabled: bool = Field(default=True, description="반려 시 피드백 입력 활성화")

    def validate_response(self, response: Dict[str, Any]) -> bool:
        """승인 응답 검증"""
        approved = response.get("approved")
        selected = response.get("selected_option", {})

        # approved 플래그 또는 선택된 옵션의 value로 판단
        return approved is not None or selected.get("value") in ("approve", "reject")

    def is_approved(self, response: Dict[str, Any]) -> bool:
        """승인 여부 판단"""
        if response.get("approved"):
            return True
        selected = response.get("selected_option", {})
        return selected.get("value") == "approve"


# =============================================================================
# InterruptFactory - 타입별 페이로드 생성 팩토리
# =============================================================================

class InterruptFactory:
    """
    인터럽트 페이로드 팩토리

    InterruptType에 따라 적절한 Payload 인스턴스를 생성합니다.
    """

    _registry: Dict[InterruptType, Type[BaseInterruptPayload]] = {
        InterruptType.OPTION: OptionInterruptPayload,
        InterruptType.OPTION_SELECTOR: OptionInterruptPayload,  # 기존 호환
        InterruptType.FORM: FormInterruptPayload,
        InterruptType.CONFIRM: ConfirmInterruptPayload,
        InterruptType.APPROVAL: ApprovalInterruptPayload,
    }

    @classmethod
    def create(
        cls,
        interrupt_type: Union[InterruptType, str],
        question: str,
        **kwargs
    ) -> BaseInterruptPayload:
        """
        인터럽트 페이로드 생성

        Args:
            interrupt_type: 인터럽트 유형 (InterruptType Enum 또는 문자열)
            question: 사용자에게 보여줄 질문
            **kwargs: 타입별 추가 파라미터
                - options: List[InterruptOption] (OPTION/APPROVAL)
                - allow_custom: bool (OPTION)
                - role: str (APPROVAL)
                - required_fields: List[str] (FORM)
                - node_ref: str (추적용 - 모든 타입)

        Returns:
            해당 타입의 BaseInterruptPayload 서브클래스 인스턴스

        Raises:
            ValueError: 지원하지 않는 인터럽트 타입

        Output JSON Examples:

        OPTION 타입:
            ```json
            {
                "type": "option",
                "question": "어떤 유형의 서비스를 원하시나요?",
                "options": [
                    {"title": "웹 앱", "description": "브라우저 기반"},
                    {"title": "모바일 앱", "description": "iOS/Android"}
                ],
                "allow_custom": true,
                "node_ref": "option_pause",
                "event_id": "evt_abc123",
                "timestamp": "2024-01-15T10:30:00"
            }
            ```

        APPROVAL 타입:
            ```json
            {
                "type": "approval",
                "question": "기획서 초안을 승인하시겠습니까?",
                "role": "팀장",
                "options": [
                    {"title": "✅ 승인", "value": "approve"},
                    {"title": "🔄 반려", "value": "reject"}
                ],
                "rejection_feedback_enabled": true,
                "node_ref": "approval_pause",
                "event_id": "evt_xyz789"
            }
            ```

        FORM 타입:
            ```json
            {
                "type": "form",
                "question": "프로젝트 상세 정보를 입력해주세요",
                "input_schema_name": "ProjectDetails",
                "required_fields": ["project_name", "budget"],
                "field_types": {"budget": "int", "deadline": "str"}
            }
            ```

        CONFIRM 타입:
            ```json
            {
                "type": "confirm",
                "question": "이대로 진행하시겠습니까?",
                "confirm_text": "예, 진행합니다",
                "cancel_text": "아니오",
                "default_value": false
            }
            ```
        """
        # 문자열 → Enum 변환
        if isinstance(interrupt_type, str):
            try:
                interrupt_type = InterruptType(interrupt_type)
            except ValueError:
                raise ValueError(f"지원하지 않는 인터럽트 타입: {interrupt_type}")

        payload_class = cls._registry.get(interrupt_type)
        if not payload_class:
            raise ValueError(f"등록되지 않은 인터럽트 타입: {interrupt_type}")

        return payload_class(question=question, **kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseInterruptPayload:
        """
        딕셔너리에서 페이로드 복원

        UI에서 받은 JSON 데이터를 Payload 객체로 변환합니다.
        """
        interrupt_type = data.get("type", InterruptType.OPTION)
        return cls.create(interrupt_type, **{k: v for k, v in data.items() if k != "type"})

    @classmethod
    def register(cls, interrupt_type: InterruptType, payload_class: Type[BaseInterruptPayload]):
        """
        새로운 인터럽트 타입 등록

        확장 시 새로운 인터럽트 타입을 런타임에 추가할 수 있습니다.

        ┌─────────────────────────────────────────────────────────────────────────┐
        │                 인터럽트 타입 확장 가이드                                │
        ├─────────────────────────────────────────────────────────────────────────┤
        │ 1. InterruptType Enum에 새 타입 추가                                   │
        │    예: FILE_UPLOAD = "file_upload"                                     │
        │                                                                         │
        │ 2. BaseInterruptPayload를 상속하는 Payload 클래스 생성                  │
        │    - validate_response() 메서드 구현 필수                              │
        │                                                                         │
        │ 3. InterruptFactory.register()로 타입 등록                             │
        │    예: InterruptFactory.register(                                      │
        │            InterruptType.FILE_UPLOAD,                                  │
        │            FileUploadInterruptPayload                                  │
        │        )                                                               │
        │                                                                         │
        │ 4. ResumeHandler에 핸들러 등록 (선택적)                                │
        │    예: ResumeHandler.register_handler(                                 │
        │            InterruptType.FILE_UPLOAD,                                  │
        │            handle_file_upload                                          │
        │        )                                                               │
        └─────────────────────────────────────────────────────────────────────────┘

        Args:
            interrupt_type: 등록할 인터럽트 타입 (InterruptType Enum)
            payload_class: 페이로드 클래스 (BaseInterruptPayload 상속)

        Raises:
            TypeError: payload_class가 BaseInterruptPayload를 상속하지 않음

        Example:
            >>> # 파일 업로드 인터럽트 추가 예시
            >>> class FileUploadPayload(BaseInterruptPayload):
            ...     type: InterruptType = Field(default="file_upload")
            ...     allowed_extensions: List[str] = Field(default=[".pdf", ".docx"])
            ...
            ...     def validate_response(self, response: Dict) -> bool:
            ...         return "file_path" in response
            ...
            >>> InterruptFactory.register(InterruptType.FILE_UPLOAD, FileUploadPayload)
        """
        if not issubclass(payload_class, BaseInterruptPayload):
            raise TypeError(
                f"payload_class는 BaseInterruptPayload를 상속해야 합니다. "
                f"받은 타입: {payload_class}"
            )
        cls._registry[interrupt_type] = payload_class

    @classmethod
    def get_registered_types(cls) -> List[InterruptType]:
        """등록된 모든 인터럽트 타입 반환"""
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, interrupt_type: Union[InterruptType, str]) -> bool:
        """인터럽트 타입 등록 여부 확인"""
        if isinstance(interrupt_type, str):
            try:
                interrupt_type = InterruptType(interrupt_type)
            except ValueError:
                return False
        return interrupt_type in cls._registry

    # =========================================================================
    # 편의 생성자 메서드 (Convenience Factory Methods)
    # =========================================================================
    # 자주 사용되는 패턴을 위한 간편 메서드들
    
    @classmethod
    def option(
        cls,
        question: str,
        options: List[Union[Dict[str, str], InterruptOption]],
        allow_custom: bool = True,
        node_ref: str = None,
        metadata: Dict[str, Any] = None,
        interrupt_id: str = None
    ) -> OptionInterruptPayload:
        """
        옵션 선택 인터럽트 간편 생성
        
        Args:
            question: 질문 텍스트
            options: 옵션 목록 (dict 또는 InterruptOption)
            allow_custom: 직접 입력 허용 여부 (기본 True)
            node_ref: 노드 참조명 (디버깅용)
            metadata: 추가 메타데이터
            
        Returns:
            OptionInterruptPayload
            
        Example:
            >>> payload = InterruptFactory.option(
            ...     question="어떤 유형을 선택하시겠습니까?",
            ...     options=[
            ...         {"title": "웹 앱", "description": "브라우저 기반"},
            ...         {"title": "모바일 앱", "description": "iOS/Android"}
            ...     ]
            ... )
        """
        normalized_options = normalize_options(options)
        import uuid
        import datetime

        return OptionInterruptPayload(
            question=question,
            options=normalized_options,
            allow_custom=allow_custom,
            node_ref=node_ref or "option_pause",
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.datetime.now().isoformat(),
            data=metadata or {},
            interrupt_id=interrupt_id
        )
    
    @classmethod
    def form(
        cls,
        question: str,
        schema_name: str,
        required_fields: List[str] = None,
        field_types: Dict[str, str] = None,
        node_ref: str = None,
        interrupt_id: str = None
    ) -> FormInterruptPayload:
        """
        폼 입력 인터럽트 간편 생성
        
        Args:
            question: 질문 텍스트
            schema_name: Pydantic 스키마 이름
            required_fields: 필수 필드 목록
            field_types: 필드별 타입 힌트 (str, int, email 등)
            node_ref: 노드 참조명
            
        Returns:
            FormInterruptPayload
            
        Example:
            >>> payload = InterruptFactory.form(
            ...     question="프로젝트 정보를 입력하세요",
            ...     schema_name="ProjectInfo",
            ...     required_fields=["name", "budget"]
            ... )
        """
        import uuid
        import datetime

        return FormInterruptPayload(
            question=question,
            input_schema_name=schema_name,
            required_fields=required_fields or [],
            field_types=field_types or {},
            node_ref=node_ref or "form_pause",
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.datetime.now().isoformat(),
            interrupt_id=interrupt_id
        )
    
    @classmethod
    def confirm(
        cls,
        question: str,
        confirm_text: str = "예",
        cancel_text: str = "아니오",
        default_value: bool = False,
        node_ref: str = None,
        interrupt_id: str = None
    ) -> ConfirmInterruptPayload:
        """
        확인(예/아니오) 인터럽트 간편 생성
        
        Args:
            question: 확인 질문
            confirm_text: 확인 버튼 텍스트
            cancel_text: 취소 버튼 텍스트
            default_value: 기본값 (False = 아니오 선택됨)
            node_ref: 노드 참조명
            
        Returns:
            ConfirmInterruptPayload
            
        Example:
            >>> payload = InterruptFactory.confirm(
            ...     question="이 구조로 진행하시겠습니까?",
            ...     confirm_text="네, 진행합니다",
            ...     cancel_text="다시 생성"
            ... )
        """
        import uuid
        import datetime

        return ConfirmInterruptPayload(
            question=question,
            confirm_text=confirm_text,
            cancel_text=cancel_text,
            default_value=default_value,
            node_ref=node_ref or "confirm_pause",
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.datetime.now().isoformat(),
            interrupt_id=interrupt_id
        )
    
    @classmethod
    def approval(
        cls,
        question: str,
        role: str,
        approve_text: str = "✅ 승인",
        reject_text: str = "🔄 반려",
        rejection_feedback_enabled: bool = True,
        node_ref: str = None,
        interrupt_id: str = None
    ) -> ApprovalInterruptPayload:
        """
        역할 기반 승인 인터럽트 간편 생성
        
        Args:
            question: 승인 요청 질문
            role: 승인자 역할 (팀장, 리더, QA 등)
            approve_text: 승인 버튼 텍스트
            reject_text: 반려 버튼 텍스트
            rejection_feedback_enabled: 반려 시 피드백 입력 활성화
            node_ref: 노드 참조명
            
        Returns:
            ApprovalInterruptPayload
            
        Example:
            >>> payload = InterruptFactory.approval(
            ...     question="기획서를 최종 승인하시겠습니까?",
            ...     role="팀장",
            ...     approve_text="승인 완료",
            ...     reject_text="수정 요청"
            ... )
        """
        import uuid
        import datetime

        return ApprovalInterruptPayload(
            question=question,
            role=role,
            options=[
                InterruptOption(title=approve_text, value="approve", description="진행합니다"),
                InterruptOption(title=reject_text, value="reject", description="수정이 필요합니다")
            ],
            rejection_feedback_enabled=rejection_feedback_enabled,
            node_ref=node_ref or f"{role.lower()}_approval",
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.datetime.now().isoformat(),
            interrupt_id=interrupt_id
        )


# =============================================================================
# Resume Handler - 응답 처리 유틸리티
# =============================================================================

class ResumeHandler:
    """
    인터럽트 응답 처리 핸들러

    각 인터럽트 타입별 응답 처리 로직을 캡슐화합니다.
    """

    @staticmethod
    def handle_option(response: Dict[str, Any]) -> Dict[str, Any]:
        """옵션 선택 응답 처리"""
        return {
            "selected_option": response.get("selected_option"),
            "text_input": response.get("text_input"),
            "action": "option_selected"
        }

    @staticmethod
    def handle_form(response: Dict[str, Any]) -> Dict[str, Any]:
        """폼 입력 응답 처리"""
        return {
            "form_data": response,
            "action": "form_submitted"
        }

    @staticmethod
    def handle_confirm(response: Dict[str, Any]) -> Dict[str, Any]:
        """확인 응답 처리"""
        return {
            "confirmed": response.get("confirmed", False),
            "action": "confirmed" if response.get("confirmed") else "cancelled"
        }

    @staticmethod
    def handle_approval(response: Dict[str, Any]) -> Dict[str, Any]:
        """승인 응답 처리"""
        approved = response.get("approved", False)
        selected = response.get("selected_option", {})

        is_approved = approved or selected.get("value") == "approve"

        return {
            "approved": is_approved,
            "rejection_reason": response.get("rejection_reason", "") if not is_approved else "",
            "action": "approved" if is_approved else "rejected"
        }

    _handlers = {
        InterruptType.OPTION: handle_option,
        InterruptType.OPTION_SELECTOR: handle_option,
        InterruptType.FORM: handle_form,
        InterruptType.CONFIRM: handle_confirm,
        InterruptType.APPROVAL: handle_approval,
    }

    @classmethod
    def handle(cls, interrupt_type: Union[InterruptType, str], response: Dict[str, Any]) -> Dict[str, Any]:
        """
        타입에 맞는 핸들러로 응답 처리

        Args:
            interrupt_type: 인터럽트 유형
            response: 사용자 응답 데이터 (UI에서 전달)

        Returns:
            정규화된 응답 딕셔너리 (action 필드 포함)

        Input/Output Examples:

        OPTION 타입:
            Input:
                ```json
                {"selected_option": {"title": "웹 앱", "description": "..."}}
                ```
            Output:
                ```json
                {
                    "selected_option": {"title": "웹 앱", "description": "..."},
                    "text_input": null,
                    "action": "option_selected"
                }
                ```

        APPROVAL 타입:
            Input (승인):
                ```json
                {"selected_option": {"title": "승인", "value": "approve"}}
                ```
            Output:
                ```json
                {"approved": true, "rejection_reason": "", "action": "approved"}
                ```

            Input (반려):
                ```json
                {
                    "selected_option": {"value": "reject"},
                    "rejection_reason": "BM 섹션 보강 필요"
                }
                ```
            Output:
                ```json
                {
                    "approved": false,
                    "rejection_reason": "BM 섹션 보강 필요",
                    "action": "rejected"
                }
                ```

        CONFIRM 타입:
            Input:
                ```json
                {"confirmed": true}
                ```
            Output:
                ```json
                {"confirmed": true, "action": "confirmed"}
                ```

        FORM 타입:
            Input:
                ```json
                {"project_name": "AI 헬스케어", "budget": 50000000}
                ```
            Output:
                ```json
                {
                    "form_data": {"project_name": "AI 헬스케어", "budget": 50000000},
                    "action": "form_submitted"
                }
                ```
        """
        if isinstance(interrupt_type, str):
            interrupt_type = InterruptType(interrupt_type)

        handler = cls._handlers.get(interrupt_type, cls.handle_option)
        return handler.__func__(response)  # staticmethod 호출

    @classmethod
    def register_handler(
        cls,
        interrupt_type: InterruptType,
        handler: callable
    ):
        """
        새로운 응답 핸들러 등록

        Args:
            interrupt_type: 인터럽트 타입
            handler: 응답 처리 함수 (Dict[str, Any]) -> Dict[str, Any]

        Example:
            >>> def handle_file_upload(response: Dict) -> Dict:
            ...     return {
            ...         "file_path": response.get("file_path"),
            ...         "file_size": response.get("file_size"),
            ...         "action": "file_uploaded"
            ...     }
            >>> ResumeHandler.register_handler(
            ...     InterruptType.FILE_UPLOAD,
            ...     handle_file_upload
            ... )
        """
        cls._handlers[interrupt_type] = staticmethod(handler)


# =============================================================================
# 기존 코드 호환성 유틸리티
# =============================================================================

def create_option_payload_compat(
    question: str,
    options: List[Dict[str, str]],
    **kwargs
) -> Dict[str, Any]:
    """
    기존 코드 호환용 옵션 페이로드 생성

    기존 create_interrupt_payload 함수와 동일한 인터페이스를 제공합니다.
    """
    interrupt_options = [
        InterruptOption(
            title=opt.get("title", ""),
            description=opt.get("description", "")
        )
        for opt in options
    ]

    payload = OptionInterruptPayload(
        question=question,
        options=interrupt_options,
        data=kwargs.get("metadata", {})
    )

    return payload.to_dict()


# =============================================================================
# Resume Value Schema (개선 3: Pydantic 기반 Resume 값 검증)
# =============================================================================

class BaseResumeValue(BaseModel):
    """
    Resume 값 베이스 클래스

    모든 Resume 타입이 상속하는 기반 클래스입니다.
    UI/API에서 자동 검증 및 폼 생성에 활용됩니다.
    """
    model_config = ConfigDict(extra="allow")  # 추가 필드 허용


class OptionResumeValue(BaseResumeValue):
    """
    옵션 선택 Resume 값

    JSON Schema:
        ```json
        {
            "selected_option": {"title": "웹 앱", "description": "브라우저 기반"},
            "text_input": null
        }
        ```
    """
    selected_option: Optional[Dict[str, Any]] = Field(
        default=None,
        description="선택된 옵션 (title, description, value 포함)"
    )
    text_input: Optional[str] = Field(
        default=None,
        description="직접 입력 텍스트 (allow_custom=True 시)"
    )

    @model_validator(mode="after")
    def validate_has_selection(self) -> Self:
        """옵션 선택 또는 직접 입력 중 하나는 있어야 함"""
        if not self.selected_option and not self.text_input:
            validate_or_warn(
                field="OptionResumeValue",
                reason="selected_option 또는 text_input 중 하나는 필수입니다",
                original_value=self.model_dump()
            )
        return self


class FormResumeValue(BaseResumeValue):
    """
    폼 입력 Resume 값

    동적 필드를 허용하며, 스키마에 정의된 필수 필드를 검증합니다.

    JSON Schema (예시):
        ```json
        {
            "project_name": "AI 헬스케어",
            "budget": 50000000,
            "deadline": "2024-06-01"
        }
        ```
    """
    # 동적 필드는 extra="allow"로 처리됨

    @classmethod
    def validate_against_schema(
        cls,
        data: Dict[str, Any],
        required_fields: List[str],
        field_types: Dict[str, str] = None
    ) -> "FormResumeValue":
        """
        스키마 기반 검증

        Args:
            data: 폼 데이터
            required_fields: 필수 필드 목록
            field_types: 필드별 타입 힌트

        Returns:
            검증된 FormResumeValue

        Raises:
            HITLValidationError: STRICT 모드에서 필수 필드 누락 시
        """
        # 필수 필드 검증
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == "":
                validate_or_warn(
                    field=field,
                    reason=f"필수 필드 누락 또는 비어있음",
                    original_value=data.get(field)
                )

        # 타입 검증
        if field_types:
            type_validators = {
                "str": lambda v: isinstance(v, str),
                "int": lambda v: isinstance(v, int) or (isinstance(v, str) and v.isdigit()),
                "float": lambda v: isinstance(v, (int, float)),
                "bool": lambda v: isinstance(v, bool),
                "email": lambda v: isinstance(v, str) and "@" in v and "." in v,
            }
            for field, expected_type in field_types.items():
                if field in data and data[field] is not None:
                    validator = type_validators.get(expected_type)
                    if validator and not validator(data[field]):
                        validate_or_warn(
                            field=field,
                            reason=f"타입 불일치 (기대: {expected_type})",
                            original_value=data[field]
                        )

        return cls(**data)


class ConfirmResumeValue(BaseResumeValue):
    """
    확인 Resume 값

    JSON Schema:
        ```json
        {"confirmed": true}
        ```
    """
    confirmed: bool = Field(description="확인 여부")


class ApprovalResumeValue(BaseResumeValue):
    """
    승인 Resume 값

    JSON Schema:
        ```json
        {
            "approved": true,
            "selected_option": {"title": "승인", "value": "approve"},
            "rejection_reason": ""
        }
        ```
    """
    approved: Optional[bool] = Field(default=None, description="승인 여부")
    selected_option: Optional[Dict[str, Any]] = Field(
        default=None,
        description="선택된 옵션 (approve/reject)"
    )
    rejection_reason: Optional[str] = Field(
        default="",
        description="반려 사유 (rejection_feedback_enabled=True 시)"
    )

    @model_validator(mode="after")
    def validate_approval_state(self) -> Self:
        """승인 상태 검증"""
        # approved 플래그 또는 selected_option 중 하나는 있어야 함
        has_approved_flag = self.approved is not None
        has_selection = self.selected_option and self.selected_option.get("value")

        if not has_approved_flag and not has_selection:
            validate_or_warn(
                field="ApprovalResumeValue",
                reason="approved 또는 selected_option.value 중 하나는 필수입니다",
                original_value=self.model_dump()
            )
        return self

    def is_approved(self) -> bool:
        """승인 여부 반환"""
        if self.approved is True:
            return True
        if self.selected_option and self.selected_option.get("value") == "approve":
            return True
        return False


# Resume Value Registry (타입별 스키마 매핑)
RESUME_VALUE_SCHEMAS: Dict[InterruptType, Type[BaseResumeValue]] = {
    InterruptType.OPTION: OptionResumeValue,
    InterruptType.OPTION_SELECTOR: OptionResumeValue,
    InterruptType.FORM: FormResumeValue,
    InterruptType.CONFIRM: ConfirmResumeValue,
    InterruptType.APPROVAL: ApprovalResumeValue,
}


def validate_resume_value(
    interrupt_type: Union[InterruptType, str],
    data: Dict[str, Any],
    payload: BaseInterruptPayload = None
) -> BaseResumeValue:
    """
    Resume 값을 타입별 스키마로 검증

    Args:
        interrupt_type: 인터럽트 타입
        data: Resume 데이터
        payload: 원본 Payload (Form 검증 시 필수 필드 정보 사용)

    Returns:
        검증된 Resume 값 객체

    Raises:
        HITLValidationError: STRICT 모드에서 검증 실패 시

    Example:
        >>> resume = validate_resume_value(
        ...     InterruptType.OPTION,
        ...     {"selected_option": {"title": "웹 앱"}}
        ... )
        >>> print(resume.selected_option["title"])
        "웹 앱"
    """
    if isinstance(interrupt_type, str):
        interrupt_type = InterruptType(interrupt_type)

    schema_class = RESUME_VALUE_SCHEMAS.get(interrupt_type, BaseResumeValue)

    # Form 타입은 payload에서 필수 필드 정보를 가져와 검증
    if interrupt_type == InterruptType.FORM and payload:
        if isinstance(payload, FormInterruptPayload):
            return FormResumeValue.validate_against_schema(
                data,
                required_fields=payload.required_fields,
                field_types=payload.field_types
            )

    return schema_class(**data)


# =============================================================================
# Interrupt Chain Visualization (개선 2: UI Timeline)
# =============================================================================

class InterruptChainEvent(BaseModel):
    """
    인터럽트 체인 이벤트

    인터럽트/Resume 이벤트를 추적하여 타임라인 시각화에 사용합니다.
    """
    event_type: str = Field(description="이벤트 타입 (PAUSE | RESUME)")
    interrupt_type: str = Field(description="인터럽트 타입")
    node_ref: str = Field(default="", description="노드 참조")
    event_id: str = Field(default="", description="이벤트 ID")
    timestamp: str = Field(default="", description="발생 시각")
    summary: str = Field(default="", description="이벤트 요약")
    data: Dict[str, Any] = Field(default_factory=dict, description="이벤트 데이터")


class InterruptChain(BaseModel):
    """
    인터럽트 체인 (전체 HITL 세션 추적)

    여러 인터럽트/Resume 이벤트를 체인으로 연결하여
    전체 HITL 흐름을 시각화합니다.
    """
    chain_id: str = Field(description="체인 ID (thread_id 기반)")
    events: List[InterruptChainEvent] = Field(default_factory=list)
    started_at: Optional[str] = Field(default=None)
    completed_at: Optional[str] = Field(default=None)

    def add_pause_event(
        self,
        payload: BaseInterruptPayload,
        node_ref: str = ""
    ):
        """인터럽트 발생 이벤트 추가"""
        import datetime

        event = InterruptChainEvent(
            event_type="PAUSE",
            interrupt_type=payload.type.value if hasattr(payload.type, 'value') else str(payload.type),
            node_ref=node_ref or payload.node_ref or "",
            event_id=payload.event_id or "",
            timestamp=datetime.datetime.now().isoformat(),
            summary=f"[PAUSE] {payload.question[:50]}...",
            data={"question": payload.question}
        )
        self.events.append(event)

        if not self.started_at:
            self.started_at = event.timestamp

    def add_resume_event(
        self,
        interrupt_type: str,
        response: Dict[str, Any],
        node_ref: str = ""
    ):
        """Resume 이벤트 추가"""
        import datetime

        # Resume 요약 생성
        summary = self._format_resume_summary(response)

        event = InterruptChainEvent(
            event_type="RESUME",
            interrupt_type=interrupt_type,
            node_ref=node_ref,
            event_id=response.get("event_id", ""),
            timestamp=datetime.datetime.now().isoformat(),
            summary=f"[RESUME] {summary}",
            data=response
        )
        self.events.append(event)

    def complete(self):
        """체인 완료 처리"""
        import datetime
        self.completed_at = datetime.datetime.now().isoformat()

    def _format_resume_summary(self, response: Dict[str, Any]) -> str:
        """Resume 응답 요약"""
        selected = response.get("selected_option")
        text_input = response.get("text_input")
        confirmed = response.get("confirmed")
        approved = response.get("approved")

        if selected:
            title = selected.get("title", "") if isinstance(selected, dict) else str(selected)
            return f"선택: {title}"
        elif text_input:
            return f"입력: {text_input[:30]}..."
        elif confirmed is not None:
            return "확인" if confirmed else "취소"
        elif approved is not None:
            return "승인" if approved else "반려"
        return "응답"

    def to_mermaid_timeline(self) -> str:
        """
        Mermaid 타임라인 다이어그램 생성

        Returns:
            Mermaid 타임라인 문자열

        Example Output:
            ```mermaid
            timeline
                title HITL Chain: thread_abc123
                section 인터럽트 흐름
                    10:30 : [PAUSE] 서비스 유형 선택
                    10:31 : [RESUME] 선택: 웹 앱
                    10:32 : [PAUSE] 상세 정보 입력
                    10:35 : [RESUME] 입력: AI 헬스케어...
            ```
        """
        lines = [
            "```mermaid",
            "timeline",
            f"    title HITL Chain: {self.chain_id[:20]}",
            "    section 인터럽트 흐름"
        ]

        for event in self.events:
            # 타임스탬프에서 시간 추출
            time_part = event.timestamp.split("T")[1][:5] if "T" in event.timestamp else ""
            lines.append(f"        {time_part} : {event.summary}")

        lines.append("```")
        return "\n".join(lines)

    def to_mermaid_sequence(self) -> str:
        """
        Mermaid 시퀀스 다이어그램 생성

        Returns:
            Mermaid 시퀀스 다이어그램 문자열

        Example Output:
            ```mermaid
            sequenceDiagram
                participant U as User
                participant S as System

                S->>U: [option_pause] 서비스 유형 선택
                U->>S: 선택: 웹 앱
                S->>U: [form_pause] 상세 정보 입력
                U->>S: 입력: AI 헬스케어
            ```
        """
        lines = [
            "```mermaid",
            "sequenceDiagram",
            "    participant U as User",
            "    participant S as System",
            ""
        ]

        for event in self.events:
            node = event.node_ref or "system"
            if event.event_type == "PAUSE":
                # 시스템이 사용자에게 질문
                question = event.data.get("question", "")[:40]
                lines.append(f"    S->>U: [{node}] {question}")
            else:
                # 사용자가 시스템에 응답
                summary = event.summary.replace("[RESUME] ", "")
                lines.append(f"    U->>S: {summary}")

        lines.append("```")
        return "\n".join(lines)


# 전역 체인 저장소 (thread_id → InterruptChain)
_INTERRUPT_CHAINS: Dict[str, InterruptChain] = {}


def get_or_create_chain(thread_id: str) -> InterruptChain:
    """스레드별 인터럽트 체인 가져오기 또는 생성"""
    if thread_id not in _INTERRUPT_CHAINS:
        _INTERRUPT_CHAINS[thread_id] = InterruptChain(chain_id=thread_id)
    return _INTERRUPT_CHAINS[thread_id]


def get_chain(thread_id: str) -> Optional[InterruptChain]:
    """스레드별 인터럽트 체인 가져오기"""
    return _INTERRUPT_CHAINS.get(thread_id)


def clear_chain(thread_id: str):
    """스레드별 인터럽트 체인 삭제"""
    if thread_id in _INTERRUPT_CHAINS:
        del _INTERRUPT_CHAINS[thread_id]
