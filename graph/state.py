"""
PlanCraft Agent - 상태 정의 모듈 (Pydantic Ver)

LangGraph 워크플로우에서 사용하는 상태(State) 타입을 Pydantic BaseModel로 정의합니다.
런타임 타입 검증과 IDE 자동완성을 지원하며, 더욱 견고한 파이프라인을 구성합니다.
"""

from typing import Optional, List, Dict, Any, Union, Self
from pydantic import BaseModel, Field, model_validator
from utils.schemas import (
    AnalysisResult, 
    StructureResult, 
    DraftResult, 
    JudgeResult, 
    OptionChoice
)

class PlanCraftState(BaseModel):
    """
    PlanCraft Agent의 워크플로우 상태 정의 (Pydantic Model)
    
    모든 상태를 Pydantic 객체로 관리하여 런타임 타입 검증과 
    IDE 자동완성 지원을 강화합니다.
    """
    # 1. 입력 상태 (Inputs)
    user_input: str = Field(description="사용자의 초기 요구사항 입력")
    file_content: Optional[str] = Field(default=None, description="업로드된 파일 내용")
    
    # 2. 컨텍스트 (Context)
    rag_context: Optional[str] = Field(default=None, description="RAG 검색 결과")
    web_context: Optional[str] = Field(default=None, description="웹 검색 결과")
    web_urls: Optional[List[str]] = Field(default=None, description="조회한 URL 목록")

    # 3. 분석 단계 (Analysis)
    analysis: Optional[AnalysisResult] = Field(default=None, description="분석 결과 객체")
    need_more_info: bool = Field(default=False, description="추가 정보 필요 여부")
    options: List[OptionChoice] = Field(default_factory=list, description="사용자 선택 옵션들")
    option_question: Optional[str] = Field(default=None, description="옵션 질문")
    selected_option: Optional[str] = Field(default=None, description="사용자가 선택한 옵션")

    # 4. 메모리 (Memory)
    # 딕셔너리 리스트로 유지 (LangChain 메시지 포맷 호환)
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

    @model_validator(mode='after')
    def sync_analysis_fields(self) -> Self:
        """
        Cross-field validation: analysis 객체와 상위 필드 동기화
        
        - analysis.need_more_info -> self.need_more_info 동기화
        - analysis.options -> self.options 동기화
        - error 발생 시 current_step 보정
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
        
        # error가 있으면 current_step에 "_error" suffix 추가 (이미 없는 경우)
        if self.error and not self.current_step.endswith("_error"):
            self.current_step = f"{self.current_step}_error"
        
        return self


def create_initial_state(user_input: str, file_content: str = None, previous_plan: str = None) -> PlanCraftState:
    """
    초기 상태를 생성합니다.
    Refinement 상황일 경우 previous_plan을 주입받습니다.
    """
    return PlanCraftState(
        user_input=user_input,
        file_content=file_content,
        previous_plan=previous_plan,
        messages=[{"role": "user", "content": user_input}]
    )
