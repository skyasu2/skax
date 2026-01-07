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

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationInfo
from typing import List, Optional, Self, Literal, Dict, Any


# =============================================================================
# Analyzer Agent 스키마
# =============================================================================

class IntentSlots(BaseModel):
    """
    의도 명확성 검사를 위한 슬롯 정보

    사용자 입력에서 추출한 핵심 정보를 구조화합니다.
    길이가 아닌 '정보 완전성'으로 HITL 필요 여부를 판단합니다.

    Attributes:
        target: 대상 (누구를 위한 서비스인가?)
        purpose: 목적 (무엇을 해결하려 하는가?)
        output_type: 산출물 형태 (앱, 웹, 사업계획서 등)
    """
    target: Optional[str] = Field(default=None, description="대상 (누구를 위한?)")
    purpose: Optional[str] = Field(default=None, description="목적 (무엇을 위해?)")
    output_type: Optional[str] = Field(default=None, description="산출물 형태 (앱, 웹, 서비스 등)")


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
    key_features: List[str] = Field(default_factory=list, description="파악된 주요 기능들 (최소 5개 이상, 구체적으로 작성)")
    user_constraints: List[str] = Field(default_factory=list, description="사용자가 명시한 제약조건/요구사항")
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

    # [NEW] 슬롯 기반 의도 명확성 검사
    intent_slots: Optional[IntentSlots] = Field(
        default=None,
        description="추출된 의도 슬롯 (target, purpose, output_type)"
    )
    missing_slots: List[str] = Field(
        default_factory=list,
        description="누락된 슬롯 목록 (예: ['target', 'purpose'])"
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="누락된 슬롯에 대한 구체적 질문 (최대 2개)"
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
        target_sections: 수정이 필요한 섹션 목록
        reasoning: 판정 이유 (1-2문장)
        feedback_summary: 전반적인 피드백 요약 (Refiner/Analyzer 참조용)
    """
    overall_score: int = Field(ge=1, le=10, description="전체 점수 (1-10)")
    verdict: str = Field(description="판정: PASS, REVISE, FAIL")
    critical_issues: List[str] = Field(default_factory=list, description="치명적 문제들")
    strengths: List[str] = Field(default_factory=list, description="잘된 점들")
    weaknesses: List[str] = Field(default_factory=list, description="약한 점들")
    action_items: List[str] = Field(default_factory=list, description="구체적 수정 지시")
    target_sections: List[str] = Field(default_factory=list, description="수정이 필요한 섹션 이름 또는 ID 목록")
    reasoning: str = Field(default="", description="판정 이유")
    feedback_summary: str = Field(default="", description="전반적인 피드백 요약 (Refiner/Analyzer 참조용)")

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
        elif 'FAIL' in v_upper:
            return 'FAIL'
        return 'REVISE'  # 기본값


class RefinementStrategy(BaseModel):
    """
    기획서 개선 전략 (Refiner Agent Output)
    """
    overall_direction: str = Field(description="전반적인 수정 방향성 (예: 논리적 허점 보완, 구체적 예시 추가)")
    key_focus_areas: List[str] = Field(description="중점적으로 보완해야 할 핵심 영역 (최대 3개)")
    specific_guidelines: List[str] = Field(description="Writer에게 전달할 구체적인 수정 지침 목록")
    additional_search_keywords: List[str] = Field(description="내용 보강을 위해 추가 검색이 필요한 키워드", default_factory=list)


# 하위 호환성을 위한 별칭
ReviewResult = JudgeResult


class UserInputSchema(BaseModel):
    """
    [NEW] 사용자 입력 처리를 위한 범용 스키마
    
    Human Interrupt 시 사용자에게 요구할 입력 형식을 정의합니다.
    UI 생성기(dynamic_form.py)가 이 스키마를 읽어 자동으로 폼을 렌더링합니다.
    """
    user_feedback: str = Field(..., description="사용자 의견이나 피드백을 입력하세요")
    # 선택지, 파일 등 확장을 위한 필드를 Optional로 정의
    selected_options: List[str] = Field(default=[], description="선택한 옵션 목록")


class InterruptPayload(BaseModel):
    """
    [NEW] 휴먼 인터럽트 페이로드
    
    LangGraph의 interrupt() 함수에 전달되어 UI가 렌더링할 내용을 정의합니다.
    """
    type: str = Field(..., description="인터럽트 유형 (option, form, confirm)")
    question: str = Field(..., description="사용자에게 보여줄 질문")
    options: List[OptionChoice] = Field(default_factory=list, description="선택 가능한 옵션 (type='option'일 때)")
    input_schema_name: Optional[str] = Field(default=None, description="입력 폼 스키마 (type='form'일 때)")
    data: Dict[str, Any] = Field(default_factory=dict, description="기타 메타데이터")


# =============================================================================
# Idea Generator 스키마 (New)
# =============================================================================

class CreativeIdea(BaseModel):
    """생성된 아이디어 항목"""
    title: str = Field(description="아이디어 제목 (매력적으로, 이모지 포함 가능)")
    description: str = Field(description="에이전트에게 전달할 구체적 기획 요청 프롬프트")

class CreativeIdeaList(BaseModel):
    """아이디어 목록"""
    ideas: List[CreativeIdea] = Field(description="생성된 아이디어 목록 (보통 3개)")

class AgentResponse(BaseModel):
    """에이전트 응답 기본 스키마"""
    final_output: str
    need_more_info: bool = False
    options: Optional[List[Dict[str, str]]] = None

class ResumeInput(BaseModel):
    """
    [HITL] 사용자 Resume 입력 검증 스키마
    - selected_option: 옵션 선택 시 (dict 형태: id, title, description)
    - text_input: 직접 입력 시 (str)
    """
    selected_option: Optional[Dict[str, str]] = Field(None, description="선택된 옵션 데이터")
    text_input: Optional[str] = Field(None, description="사용자 직접 입력 텍스트")

    @field_validator('selected_option', 'text_input')
    @classmethod
    def check_at_least_one(cls, v: Optional[Any], info: ValidationInfo) -> Optional[Any]:
        # Pydantic v2에서는 validator가 필드별로 호출되므로, 다른 필드의 값을 직접 참조하기 어려움.
        # 이 검증은 model_validator에서 하는 것이 더 적합함.
        # 여기서는 단순히 값을 반환하고, 실제 "하나 이상 존재" 로직은 model_validator에서 처리하거나
        # 이 스키마를 사용하는 로직에서 처리하는 것이 권장됨.
        return v

    @model_validator(mode='after')
    def validate_at_least_one_input(self) -> Self:
        if self.selected_option is None and self.text_input is None:
            raise ValueError("selected_option 또는 text_input 중 하나는 반드시 제공되어야 합니다.")
        return self


# =============================================================================
# Discussion & Consensus 스키마 (Multi-Agent Collaboration)
# =============================================================================

class ConsensusResult(BaseModel):
    """
    LLM 기반 합의 판정 결과

    Reviewer-Writer 대화에서 실제로 합의가 이루어졌는지 LLM이 판단합니다.
    키워드 기반이 아닌 의미론적 분석으로 더 정확한 합의 감지가 가능합니다.
    """
    consensus_reached: bool = Field(description="합의 도달 여부")
    confidence: float = Field(ge=0.0, le=1.0, description="합의 판정 신뢰도 (0.0~1.0)")
    agreed_items: List[str] = Field(default_factory=list, description="합의된 개선 사항 목록")
    unresolved_items: List[str] = Field(default_factory=list, description="미해결 사항 목록")
    reasoning: str = Field(default="", description="합의 판정 이유")
    suggested_next_action: str = Field(
        default="continue",
        description="다음 액션 제안: continue(대화 계속), finalize(합의 완료), escalate(사용자 개입 필요)"
    )


class DataGapRequest(BaseModel):
    """
    Writer가 작성 중 발견한 데이터 부족 요청

    Writer가 특정 섹션 작성 시 데이터가 부족하면
    Specialist에게 추가 분석을 요청할 수 있습니다.
    """
    requesting_section: str = Field(description="요청하는 섹션명")
    target_specialist: str = Field(description="요청 대상 Specialist (market, bm, financial, risk, tech)")
    query: str = Field(description="구체적인 데이터 요청 내용")
    priority: str = Field(default="normal", description="우선순위: high, normal, low")
    context: str = Field(default="", description="요청 배경 설명")


class DataGapAnalysis(BaseModel):
    """
    Writer의 데이터 부족 분석 결과

    Writer가 초안 작성 전 데이터 완전성을 검사하고
    부족한 데이터가 있으면 Specialist에게 요청 목록을 생성합니다.
    """
    has_gaps: bool = Field(description="데이터 부족 여부")
    gap_requests: List[DataGapRequest] = Field(default_factory=list, description="데이터 요청 목록")
    can_proceed_with_assumptions: bool = Field(
        default=True,
        description="가정으로 진행 가능 여부 (True면 요청 없이도 진행 가능)"
    )
    assumptions_if_proceed: List[str] = Field(
        default_factory=list,
        description="가정으로 진행 시 세울 가정들"
    )


class SpecialistResponse(BaseModel):
    """
    Specialist의 추가 데이터 응답

    Writer의 DataGapRequest에 대한 Specialist의 응답입니다.
    """
    request_id: str = Field(description="요청 ID (추적용)")
    specialist_id: str = Field(description="응답한 Specialist ID")
    data: Dict[str, Any] = Field(description="요청된 데이터")
    confidence: float = Field(ge=0.0, le=1.0, default=0.8, description="데이터 신뢰도")
    sources: List[str] = Field(default_factory=list, description="데이터 출처")
