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

사용 예시:
    from graph.interrupt_types import InterruptFactory, InterruptType

    # 옵션 인터럽트 생성
    payload = InterruptFactory.create(
        InterruptType.OPTION,
        question="방향을 선택하세요",
        options=[{"title": "A", "description": "설명A"}]
    )

    # interrupt() 호출에 사용
    user_response = interrupt(payload.to_dict())
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Any, Optional, Union, Type
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing_extensions import Self


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
    """인터럽트 옵션 항목"""
    title: str = Field(description="옵션 제목")
    description: str = Field(default="", description="옵션 설명")
    value: Optional[str] = Field(default=None, description="옵션 값 (선택적)")

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
                title=obj.get("title", ""),
                description=obj.get("description", ""),
                value=obj.get("value")
            )
        if hasattr(obj, "title") and hasattr(obj, "description"):
            # Duck typing: OptionChoice 등 호환 객체
            return cls(
                title=getattr(obj, "title", ""),
                description=getattr(obj, "description", ""),
                value=getattr(obj, "value", None)
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

    Example:
        # 혼합된 형태도 처리 가능
        options = normalize_options([
            {"title": "A", "description": "설명A"},
            InterruptOption(title="B", description="설명B"),
            some_pydantic_option_choice,  # duck-typing
        ])
    """
    normalized = []
    for opt in options:
        try:
            normalized.append(InterruptOption.from_any(opt))
        except ValueError as e:
            print(f"[WARN] 옵션 변환 실패: {e}")
            # 실패 시 기본 옵션으로 대체
            normalized.append(InterruptOption(title=str(opt), description=""))
    return normalized


class BaseInterruptPayload(BaseModel, ABC):
    """
    인터럽트 페이로드 베이스 클래스

    모든 인터럽트 타입이 상속하는 추상 기반 클래스입니다.
    공통 필드와 메서드를 정의합니다.
    """
    type: InterruptType = Field(description="인터럽트 유형")
    question: str = Field(description="사용자에게 보여줄 질문")
    data: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")

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
            interrupt_type: 인터럽트 유형
            question: 사용자에게 보여줄 질문
            **kwargs: 타입별 추가 파라미터

        Returns:
            해당 타입의 BaseInterruptPayload 서브클래스 인스턴스

        Raises:
            ValueError: 지원하지 않는 인터럽트 타입
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
            response: 사용자 응답 데이터

        Returns:
            정규화된 응답 딕셔너리
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
