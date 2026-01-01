"""
PlanCraft - HITL (Human-in-the-Loop) 설정 모듈

Interrupt Payload 구조, 필드 명명 규칙, 확장 패턴을 중앙 관리합니다.

코드 리뷰 피드백 반영:
- payload 필드 표준화
- config 기반 관리
- 확장성 패턴 문서화
"""

from typing import Dict, Any, List, Optional, Callable, Type
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid


# =============================================================================
# Interrupt 타입 정의
# =============================================================================

class InterruptType(str, Enum):
    """지원하는 Interrupt 타입"""
    OPTION = "option"          # 선택지 제시
    FORM = "form"              # 폼 입력
    CONFIRM = "confirm"        # 예/아니오 확인
    APPROVAL = "approval"      # 승인 요청
    FILE_UPLOAD = "file_upload"  # 파일 업로드 (확장)
    CUSTOM = "custom"          # 커스텀 타입


# =============================================================================
# Payload 필드 표준화 (핵심!)
# =============================================================================

@dataclass
class PayloadFieldSpec:
    """페이로드 필드 명세"""
    name: str
    description: str
    required: bool = False
    default: Any = None


# 표준 필드 정의 - 모든 Interrupt Payload에 포함
STANDARD_PAYLOAD_FIELDS: Dict[str, PayloadFieldSpec] = {
    # === 식별 필드 (Tracking) ===
    "event_id": PayloadFieldSpec(
        name="event_id",
        description="인터럽트 이벤트 고유 식별자 (UUID)",
        required=True,
    ),
    "node_ref": PayloadFieldSpec(
        name="node_ref",
        description="인터럽트가 발생한 노드 이름",
        required=True,
    ),
    "timestamp": PayloadFieldSpec(
        name="timestamp",
        description="인터럽트 발생 시각 (ISO 8601)",
        required=True,
    ),
    
    # === 컨텐츠 필드 ===
    "type": PayloadFieldSpec(
        name="type",
        description="인터럽트 타입 (option/form/confirm/approval)",
        required=True,
    ),
    "question": PayloadFieldSpec(
        name="question",
        description="사용자에게 표시할 질문/메시지",
        required=True,
    ),
    
    # === 선택적 필드 ===
    "options": PayloadFieldSpec(
        name="options",
        description="선택지 목록 (option 타입용)",
        required=False,
        default=[],
    ),
    "input_schema_name": PayloadFieldSpec(
        name="input_schema_name",
        description="입력 스키마 이름 (form 타입용)",
        required=False,
    ),
    "data": PayloadFieldSpec(
        name="data",
        description="추가 데이터 (커스텀 용도)",
        required=False,
        default={},
    ),
    "error": PayloadFieldSpec(
        name="error",
        description="에러 메시지 (재시도 시)",
        required=False,
    ),
    
    # === 메타데이터 ===
    "retry_count": PayloadFieldSpec(
        name="retry_count",
        description="현재 재시도 횟수",
        required=False,
        default=0,
    ),
    "max_retries": PayloadFieldSpec(
        name="max_retries",
        description="최대 재시도 횟수",
        required=False,
        default=3,
    ),
    "thread_id": PayloadFieldSpec(
        name="thread_id",
        description="워크플로우 스레드 식별자",
        required=False,
    ),
}


# =============================================================================
# Payload 생성 유틸리티
# =============================================================================

def create_base_payload(
    interrupt_type: InterruptType,
    question: str,
    node_ref: str,
    **kwargs
) -> Dict[str, Any]:
    """
    표준 필드가 포함된 기본 페이로드 생성
    
    Args:
        interrupt_type: 인터럽트 타입
        question: 사용자에게 표시할 질문
        node_ref: 발생 노드 이름
        **kwargs: 추가 필드
        
    Returns:
        표준화된 페이로드 dict
    """
    payload = {
        # 필수 필드
        "event_id": str(uuid.uuid4()),
        "node_ref": node_ref,
        "timestamp": datetime.now().isoformat(),
        "type": interrupt_type.value,
        "question": question,
        
        # 기본값
        "options": kwargs.get("options", []),
        "input_schema_name": kwargs.get("input_schema_name"),
        "data": kwargs.get("data", {}),
        "error": kwargs.get("error"),
        "retry_count": kwargs.get("retry_count", 0),
        "max_retries": kwargs.get("max_retries", 3),
        "thread_id": kwargs.get("thread_id"),
    }
    
    # 추가 커스텀 필드
    for key, value in kwargs.items():
        if key not in payload:
            payload[key] = value
    
    return payload


def create_option_payload(
    question: str,
    options: List[Dict],
    node_ref: str,
    **kwargs
) -> Dict[str, Any]:
    """Option 타입 페이로드 생성 헬퍼"""
    return create_base_payload(
        interrupt_type=InterruptType.OPTION,
        question=question,
        node_ref=node_ref,
        options=options,
        **kwargs
    )


def create_form_payload(
    question: str,
    input_schema_name: str,
    node_ref: str,
    **kwargs
) -> Dict[str, Any]:
    """Form 타입 페이로드 생성 헬퍼"""
    return create_base_payload(
        interrupt_type=InterruptType.FORM,
        question=question,
        node_ref=node_ref,
        input_schema_name=input_schema_name,
        **kwargs
    )


def create_confirm_payload(
    question: str,
    node_ref: str,
    **kwargs
) -> Dict[str, Any]:
    """Confirm 타입 페이로드 생성 헬퍼"""
    return create_base_payload(
        interrupt_type=InterruptType.CONFIRM,
        question=question,
        node_ref=node_ref,
        options=[
            {"title": "예", "description": "진행합니다"},
            {"title": "아니오", "description": "취소합니다"},
        ],
        **kwargs
    )


def create_approval_payload(
    question: str,
    node_ref: str,
    approval_data: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """Approval 타입 페이로드 생성 헬퍼"""
    return create_base_payload(
        interrupt_type=InterruptType.APPROVAL,
        question=question,
        node_ref=node_ref,
        data=approval_data or {},
        options=[
            {"title": "승인", "description": "승인하고 다음 단계로 진행"},
            {"title": "반려", "description": "수정을 요청"},
        ],
        **kwargs
    )


# =============================================================================
# Interrupt Factory (확장 패턴)
# =============================================================================

class InterruptFactory:
    """
    Interrupt 페이로드 팩토리 (확장 가능)
    
    커스텀 인터럽트 타입 등록 패턴:
    ```python
    def custom_handler(question, node_ref, **kwargs):
        return create_base_payload(
            InterruptType.CUSTOM,
            question, node_ref,
            custom_field=kwargs.get("custom_value"),
            **kwargs
        )
    
    InterruptFactory.register("file_upload", custom_handler)
    ```
    """
    
    _handlers: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, type_name: str, handler: Callable) -> None:
        """
        새 인터럽트 타입 핸들러 등록
        
        Args:
            type_name: 타입 이름 (예: "file_upload")
            handler: 페이로드 생성 함수
        """
        cls._handlers[type_name] = handler
    
    @classmethod
    def create(cls, type_name: str, **kwargs) -> Dict[str, Any]:
        """
        등록된 핸들러로 페이로드 생성
        
        Args:
            type_name: 타입 이름
            **kwargs: 핸들러에 전달할 인자
        """
        if type_name not in cls._handlers:
            # 기본 핸들러 사용
            return create_base_payload(
                InterruptType.CUSTOM,
                kwargs.get("question", ""),
                kwargs.get("node_ref", "unknown"),
                **kwargs
            )
        return cls._handlers[type_name](**kwargs)
    
    @classmethod
    def list_types(cls) -> List[str]:
        """등록된 타입 목록"""
        builtin = [t.value for t in InterruptType]
        custom = list(cls._handlers.keys())
        return builtin + custom


# 기본 핸들러 등록
InterruptFactory.register("option", create_option_payload)
InterruptFactory.register("form", create_form_payload)
InterruptFactory.register("confirm", create_confirm_payload)
InterruptFactory.register("approval", create_approval_payload)


# =============================================================================
# Payload 검증 유틸리티
# =============================================================================

def validate_payload(payload: Dict[str, Any]) -> tuple:
    """
    페이로드 필드 검증
    
    Returns:
        (is_valid: bool, errors: List[str])
    """
    errors = []
    
    for field_name, spec in STANDARD_PAYLOAD_FIELDS.items():
        if spec.required and field_name not in payload:
            errors.append(f"필수 필드 누락: {field_name}")
    
    if not payload.get("type"):
        errors.append("type 필드가 비어있습니다")
    
    if not payload.get("question"):
        errors.append("question 필드가 비어있습니다")
    
    return (len(errors) == 0, errors)


# =============================================================================
# 상수 및 설정
# =============================================================================

# 재시도 설정
HITL_MAX_RETRIES = 3
HITL_VALIDATION_MAX_RETRIES = 5

# 타임아웃 설정 (초)
HITL_DEFAULT_TIMEOUT = 3600  # 1시간

# 지원 옵션 타입
SUPPORTED_OPTION_FIELDS = ["title", "description", "value", "icon"]

# 입력 스키마 이름 목록
REGISTERED_INPUT_SCHEMAS = [
    "additional_info_input",
    "file_upload_input",
    "custom_form_input",
]


# =============================================================================
# 문서화 (팀원 가이드)
# =============================================================================

HITL_DOCUMENTATION = """
# PlanCraft HITL (Human-in-the-Loop) 가이드

## 중요 규칙 ⚠️

### 1. Interrupt 전 Side-Effect 금지
```python
def my_node(state):
    # ❌ 잘못된 예 - interrupt 전에 DB 저장
    save_to_database(state)
    value = interrupt(payload)
    
    # ✅ 올바른 예 - interrupt 후에 Side-effect
    value = interrupt(payload)
    save_to_database(state)  # Resume 시 여기부터 실행
```

### 2. SubGraph Interrupt 주의
**SubGraph 내부에서 interrupt() 사용 시, Resume는 부모 그래프의 
해당 노드 처음부터 재실행됩니다!**

SubGraph에서 interrupt 사용 시:
1. 부모 노드가 처음부터 다시 실행됨
2. SubGraph도 처음부터 다시 실행됨
3. interrupt 전 코드가 다시 실행됨

따라서 interrupt 전 코드는 **반드시 멱등성(idempotent)** 보장!

### 3. 페이로드 표준 필드
모든 페이로드에 다음 필드 포함:
- event_id: UUID
- node_ref: 노드 이름
- timestamp: ISO 8601 시각
- type: 인터럽트 타입
- question: 질문/메시지

### 4. 확장 패턴
```python
from graph.hitl_config import InterruptFactory, InterruptType

# 커스텀 타입 등록
def file_upload_handler(question, node_ref, **kwargs):
    return create_base_payload(
        InterruptType.FILE_UPLOAD,
        question, node_ref,
        allowed_types=kwargs.get("allowed_types", [".pdf", ".docx"]),
        max_size_mb=kwargs.get("max_size_mb", 10),
    )

InterruptFactory.register("file_upload", file_upload_handler)
```

## 참고 문서
- LangGraph HITL Guide: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/
"""


def print_documentation():
    """HITL 문서 출력"""
    print(HITL_DOCUMENTATION)


# =============================================================================
# 디버깅 유틸리티
# =============================================================================

def debug_payload(payload: Dict[str, Any]) -> None:
    """페이로드 디버그 출력"""
    print("=" * 50)
    print("HITL Payload Debug")
    print("=" * 50)
    is_valid, errors = validate_payload(payload)
    print(f"Valid: {is_valid}")
    if errors:
        print(f"Errors: {errors}")
    print("-" * 50)
    for key, value in payload.items():
        print(f"  {key}: {value}")
    print("=" * 50)


if __name__ == "__main__":
    print_documentation()
    
    # 테스트
    test_payload = create_option_payload(
        question="목차를 선택하세요",
        options=[{"title": "A", "description": "옵션 A"}],
        node_ref="structure_approval"
    )
    debug_payload(test_payload)
