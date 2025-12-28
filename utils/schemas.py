"""
PlanCraft Agent - Pydantic 스키마 정의

각 Agent의 출력 형식을 정의하는 Pydantic 모델입니다.
Structured Output을 통해 LLM 응답의 일관성과 타입 안전성을 보장합니다.

스키마 목록:
    - AnalysisResult: Analyzer Agent 출력
    - SectionStructure: 기획서 섹션 구조
    - StructureResult: Structurer Agent 출력
    - SectionContent: 작성된 섹션 내용
    - DraftResult: Writer Agent 출력
    - ReviewResult: Reviewer Agent 출력

사용 예시:
    from utils.schemas import AnalysisResult
    
    # JSON에서 Pydantic 모델로 변환
    data = {"topic": "점심 추천 앱", "purpose": "메뉴 고민 해결", ...}
    analysis = AnalysisResult(**data)
    
    # 모델에서 딕셔너리로 변환
    analysis_dict = analysis.model_dump()
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Self


# =============================================================================
# Analyzer Agent 스키마
# =============================================================================

class OptionChoice(BaseModel):
    """
    사용자 선택 옵션

    추가 정보가 필요할 때 질문 대신 선택지를 제공합니다.

    Attributes:
        title: 옵션 제목 (짧은 설명)
        description: 옵션에 대한 상세 설명
    """
    title: str = Field(description="옵션 제목")
    description: str = Field(description="옵션 상세 설명")


class AnalysisResult(BaseModel):
    """
    Analyzer Agent의 출력 스키마

    사용자 입력을 분석한 결과를 구조화합니다.
    대부분의 경우 질문 없이 합리적인 가정을 세워 바로 진행합니다.

    Attributes:
        topic: 핵심 주제 (예: "사내 점심 메뉴 추천 서비스")
        purpose: 기획의 목적 (예: "메뉴 선택 고민 시간 단축")
        target_users: 예상 타겟 사용자 (예: "직장인, 20-40대")
        key_features: 파악된 주요 기능 목록
        assumptions: 에이전트가 세운 합리적인 가정들
        missing_info: 누락된 정보 목록 (보통 비어있음)
        options: 사용자가 선택할 수 있는 옵션 (핵심 방향 결정 시에만)
        option_question: 옵션 선택을 위한 질문
        need_more_info: 추가 정보 필요 여부 (대부분 False)
    """
    topic: str = Field(description="핵심 주제")
    purpose: str = Field(description="기획의 목적")
    target_users: str = Field(description="예상 타겟 사용자")
    key_features: List[str] = Field(default_factory=list, description="파악된 주요 기능들")
    assumptions: List[str] = Field(default_factory=list, description="합리적인 가정들")
    missing_info: List[str] = Field(default_factory=list, description="누락된 정보 목록")
    options: List[OptionChoice] = Field(default_factory=list, description="선택 가능한 옵션들")
    option_question: str = Field(default="", description="옵션 선택을 위한 질문")
    is_general_query: bool = Field(default=False, description="일반 질문 여부 (기획서 생성이 아님)")
    general_answer: Optional[str] = Field(default=None, description="일반 질문에 대한 직접 답변")
    
    # [추가] 문서 유형 분류
    doc_type: str = Field(
        default="web_app_plan", 
        description="생성할 문서 유형 (web_app_plan, business_plan 중 하나)"
    )
    
    need_more_info: bool = Field(default=False, description="추가 정보 필요 여부")

    @model_validator(mode='after')
    def validate_options_when_need_more_info(self) -> Self:
        """need_more_info=True일 때 options가 반드시 존재해야 함"""
        if self.need_more_info and not self.options:
            # 자동으로 기본 옵션 생성 (Fallback)
            self.options = [
                OptionChoice(title="기본 진행", description="AI가 자동으로 가정하여 진행합니다")
            ]
        return self


# =============================================================================
# Structurer Agent 스키마
# =============================================================================

class SectionStructure(BaseModel):
    """
    기획서 섹션 구조 정의
    
    각 섹션의 메타데이터를 정의합니다.
    Writer Agent에서 이 구조를 기반으로 내용을 작성합니다.
    
    Attributes:
        id: 섹션 번호 (순서)
        name: 섹션명 (예: "프로젝트 개요")
        description: 이 섹션에서 다룰 내용 설명
        key_points: 포함해야 할 핵심 포인트 목록
    """
    id: int = Field(description="섹션 번호")
    name: str = Field(description="섹션명")
    description: str = Field(default="", description="섹션 설명")
    key_points: List[str] = Field(default_factory=list, description="핵심 포인트")


class StructureResult(BaseModel):
    """
    Structurer Agent의 출력 스키마
    
    기획서의 전체 구조를 정의합니다.
    
    Attributes:
        title: 기획서 제목
        sections: 섹션 목록 (SectionStructure 리스트)
    """
    title: str = Field(description="기획서 제목")
    sections: List[SectionStructure] = Field(description="섹션 목록")

    @field_validator('sections')
    @classmethod
    def validate_sections_not_empty(cls, v: List[SectionStructure]) -> List[SectionStructure]:
        """sections는 최소 1개 이상 필요"""
        if not v:
            # 기본 섹션 생성 (Fallback)
            return [SectionStructure(id=1, name="개요", description="프로젝트 개요", key_points=[])]
        return v


# =============================================================================
# Writer Agent 스키마
# =============================================================================

class SectionContent(BaseModel):
    """
    작성된 섹션 내용
    
    Writer Agent가 작성한 각 섹션의 실제 내용입니다.
    content 필드는 마크다운 형식으로 작성됩니다.
    
    Attributes:
        id: 섹션 번호
        name: 섹션명
        content: 작성된 내용 (마크다운 형식)
    """
    id: int = Field(description="섹션 번호")
    name: str = Field(description="섹션명")
    content: str = Field(description="작성된 내용 (마크다운)")


class DraftResult(BaseModel):
    """
    Writer Agent의 출력 스키마
    
    작성된 기획서 초안 전체를 담습니다.
    
    Attributes:
        sections: 작성된 섹션들의 리스트
    """
    sections: List[SectionContent] = Field(description="작성된 섹션들")


# =============================================================================
# Reviewer(Judge) Agent 스키마
# =============================================================================

class JudgeResult(BaseModel):
    """
    Reviewer(Judge) Agent의 출력 스키마

    기획서를 냉정하게 심사하고 PASS/REVISE/FAIL 판정을 내립니다.
    이 판정은 Refiner가 적절한 수준의 개선을 하도록 가이드합니다.

    Attributes:
        overall_score: 전체 점수 (1-10)
        verdict: 판정 (PASS/REVISE/FAIL)
        critical_issues: 치명적 문제들
        strengths: 잘된 점들
        weaknesses: 약한 점들
        action_items: 구체적인 수정 지시사항
        reasoning: 판정 이유 (1-2문장)
    """
    overall_score: int = Field(ge=1, le=10, description="전체 점수 (1-10)")
    verdict: str = Field(description="판정: PASS, REVISE, FAIL")
    critical_issues: List[str] = Field(default_factory=list, description="치명적 문제들")
    strengths: List[str] = Field(default_factory=list, description="잘된 점들")
    weaknesses: List[str] = Field(default_factory=list, description="약한 점들")
    action_items: List[str] = Field(default_factory=list, description="구체적 수정 지시")
    reasoning: str = Field(default="", description="판정 이유")

    @field_validator('verdict')
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        """verdict는 반드시 PASS, REVISE, FAIL 중 하나"""
        valid_verdicts = {'PASS', 'REVISE', 'FAIL'}
        v_upper = v.upper().strip()
        if v_upper in valid_verdicts:
            return v_upper
        # 유사 값 자동 보정
        if 'PASS' in v_upper:
            return 'PASS'
        elif 'FAIL' in v_upper:
            return 'FAIL'
        return 'REVISE'  # 기본값


# 하위 호환성을 위한 별칭
ReviewResult = JudgeResult
