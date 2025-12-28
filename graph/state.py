"""
PlanCraft Agent - 상태 정의 모듈 (Pydantic Ver)

LangGraph 워크플로우에서 사용하는 상태(State) 타입을 Pydantic BaseModel로 정의합니다.
런타임 타입 검증과 IDE 자동완성을 지원하며, 더욱 견고한 파이프라인을 구성합니다.
"""

from typing import Optional, List, Dict, Any, Union, Self, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import TypedDict
from utils.schemas import (
    AnalysisResult,
    StructureResult,
    DraftResult,
    JudgeResult,
    OptionChoice,
    SectionStructure,
    SectionContent,
    ReviewResult
)

# =============================================================================
# Input / Output Schema (LangGraph Interface - TypedDict)
# =============================================================================

class PlanCraftInput(TypedDict):
    """외부에서 유입되는 입력 데이터 스키마 (TypedDict)"""
    user_input: str
    file_content: Optional[str]
    refine_count: int
    retry_count: int
    previous_plan: Optional[str]
    thread_id: str

class PlanCraftOutput(TypedDict):
    """최종적으로 반환되는 출력 데이터 스키마 (TypedDict)"""
    final_output: Optional[str]
    step_history: List[dict]
    chat_history: List[dict]
    error: Optional[str]
    error_message: Optional[str]
    retry_count: int

# =============================================================================
# Interrupt Payload Schema (Human-in-the-loop Interface)
# =============================================================================

class InterruptOption(TypedDict):
    """인터럽트 선택지 스키마"""
    title: str
    description: str

class InterruptPayload(TypedDict):
    """휴먼 인터럽트 페이로드 스키마"""
    type: str  # "option", "form", "confirm"
    question: str
    options: List[InterruptOption]
    input_schema_name: Optional[str]
    data: Optional[dict]


# =============================================================================
# Overall State (Internal State)
# =============================================================================

class PlanCraftState(BaseModel):
    """
    PlanCraft Agent 전체 상태 스키마
    
    Input + Output + Internal State를 모두 포함합니다.
    LangGraph의 StateGraph(PlanCraftState)로 사용됩니다.
    """
    # 1. 입력 데이터 (PlanCraftInput Fields)
    user_input: str = Field(description="사용자 요청 사항")
    file_content: Optional[str] = Field(default=None, description="첨부 파일 내용")
    refine_count: int = Field(default=0, description="기획서 개선 횟수")
    previous_plan: Optional[str] = Field(default=None, description="이전 기획서 내용 (개선 시)")
    thread_id: str = Field(default="default_thread", description="세션 스레드 ID")

    # 2. 출력 데이터 (PlanCraftOutput Fields)
    final_output: Optional[str] = Field(default=None, description="최종 생성된 기획서")
    step_history: List[dict] = Field(default_factory=list, description="실행 단계 이력")
    chat_history: List[dict] = Field(default_factory=list, description="채팅 기록")
    error: Optional[str] = Field(default=None, description="에러 발생 시 메시지")

    # 3. 컨텍스트 (Context)
    rag_context: Optional[str] = Field(default=None, description="RAG 검색 결과")
    web_context: Optional[str] = Field(default=None, description="웹 검색 결과")
    web_urls: Optional[List[str]] = Field(default=None, description="조회한 URL 목록")

    # 4. 분석 단계 (Analysis)
    analysis: Optional[AnalysisResult] = Field(default=None, description="분석 결과 객체")
    # [NEW] 동적 폼 생성을 위한 스키마 이름 (utils.schemas 내의 클래스명)
    input_schema_name: Optional[str] = Field(default=None, description="입력 폼 스키마 클래스명")
    
    need_more_info: bool = Field(default=False, description="추가 정보 필요 여부")
    options: List[OptionChoice] = Field(default_factory=list, description="사용자 선택 옵션들")
    option_question: Optional[str] = Field(default=None, description="옵션 질문")
    selected_option: Optional[str] = Field(default=None, description="사용자가 선택한 옵션")

    messages: List[Dict[str, str]] = Field(default_factory=list, description="대화 히스토리")

    # 5. 구조화 단계 (Structure)
    structure: Optional[StructureResult] = Field(default=None, description="기획서 구조 객체")

    # 6. 작성 단계 (Draft)
    draft: Optional[DraftResult] = Field(default=None, description="작성된 초안 객체")

    # 7. 리뷰 및 개선 (Review & Refine)
    review: Optional[JudgeResult] = Field(default=None, description="검토 결과 객체")
    refined: bool = Field(default=False, description="개선 완료 여부")

    # 8. 최종 산출물 (Outputs)
    final_output: Optional[str] = Field(default=None, description="최종 기획서 (Markdown)")
    chat_summary: Optional[str] = Field(default=None, description="채팅용 요약 메시지")

    # 9. 메타데이터 (Metadata)
    current_step: str = Field(default="start", description="현재 실행 중인 단계")
    refine_count: int = Field(default=0, description="추가 개선 수행 횟수 (최대 3회)")
    # [추가] 이전 기획서 스냅샷 (Refinement 시 참고)
    previous_plan: Optional[str] = Field(default=None, description="이전 회차의 기획서 (Markdown)")
    error: Optional[str] = Field(default=None, description="에러 메시지")

    # [NEW] 운영 가시성 (Operational Visibility)
    step_history: List[Dict[str, Any]] = Field(default_factory=list, description="실행 단계별 상태 이력 (Timeline)")
    step_status: Literal["RUNNING", "SUCCESS", "FAILED"] = Field(default="RUNNING", description="현재 단계 수행 상태")
    last_error: Optional[str] = Field(default=None, description="마지막 발생 에러")
    
    # [NEW] 시계열 기준점 (Time Context)
    execution_time: Optional[str] = Field(default=None, description="워크플로우 실행 시각 (모든 에이전트의 시계열 기준)")

    # [NEW] 에러 처리 및 재시도 (Error Handling & Retry)
    retry_count: int = Field(default=0, description="재시도 횟수")

    @model_validator(mode='after')
    def sync_analysis_fields(self) -> Self:
        """
        Cross-field validation: analysis 객체와 상위 필드 동기화
        
        - analysis.need_more_info -> self.need_more_info 동기화
        - analysis.options -> self.options 동기화
        - error 발생 시 current_step 보정 및 step_status 업데이트
        """
        # analysis 객체가 있으면 need_more_info, options 동기화
        if self.analysis is not None:
            if hasattr(self.analysis, 'need_more_info'):
                # analysis의 need_more_info가 True면 상위 상태도 동기화
                if self.analysis.need_more_info and not self.need_more_info:
                    self.need_more_info = True
            
            if hasattr(self.analysis, 'options') and self.analysis.options:
                if not self.options:
                    self.options = self.analysis.options
            
            if hasattr(self.analysis, 'option_question') and self.analysis.option_question:
                if not self.option_question:
                    self.option_question = self.analysis.option_question
        
        # error가 있으면 current_step에 "_error" suffix 추가 및 status FAILED 처리
        if self.error:
            if not self.current_step.endswith("_error"):
                self.current_step = f"{self.current_step}_error"
            if self.step_status != "FAILED":
                self.step_status = "FAILED"
        
        return self


def create_initial_state(user_input: str, file_content: str = None, previous_plan: str = None) -> PlanCraftState:
    """
    초기 상태를 생성합니다.
    Refinement 상황일 경우 previous_plan을 주입받습니다.
    """
    from datetime import datetime
    
    # [NEW] 실행 시점의 시간을 문자열로 저장
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return PlanCraftState(
        user_input=user_input,
        file_content=file_content,
        previous_plan=previous_plan,
        messages=[{"role": "user", "content": user_input}],
        execution_time=current_time  # [NEW]
    )
