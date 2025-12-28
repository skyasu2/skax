"""
PlanCraft Agent - Structurer Agent

분석 결과를 바탕으로 기획서의 섹션 구조를 설계하는 Agent입니다.
논리적인 흐름(Why -> What -> How)을 고려하여 최적의 구조를 제안합니다.

주요 기능:
    - 기획서 제목 생성
    - 섹션 구조 설계
    - 각 섹션별 핵심 포인트 정의
    - 필수/선택 섹션 구분

입력:
    - analysis: Analyzer Agent의 분석 결과
    - rag_context: RAG 검색 결과 (선택)

출력:
    - structure: 기획서 구조 딕셔너리

Best Practice 적용:
    - with_structured_output(): LangChain 표준 Structured Output 패턴
    - PlanCraftState 타입 어노테이션: 명시적 입출력 타입
"""

import json
from utils.llm import get_llm
from utils.schemas import StructureResult
from graph.state import PlanCraftState
from prompts.structurer_prompt import STRUCTURER_SYSTEM_PROMPT, STRUCTURER_USER_PROMPT


class StructurerAgent:
    """
    기획서 구조를 설계하는 Agent

    LangChain의 with_structured_output()을 사용하여
    Pydantic 스키마 기반의 구조화된 출력을 생성합니다.

    Attributes:
        llm: AzureChatOpenAI 인스턴스 (Structured Output 적용)
    """

    def __init__(self, model_type: str = "gpt-4o"):
        """
        Structurer Agent를 초기화합니다.

        Args:
            model_type: 사용할 LLM 모델
        """
        # 구조 설계는 적당한 창의성 필요
        base_llm = get_llm(model_type=model_type, temperature=0.5)

        # with_structured_output: LangChain Best Practice
        self.llm = base_llm.with_structured_output(StructureResult)

    def run(self, state: PlanCraftState) -> PlanCraftState:
        """
        기획서 구조를 설계합니다.

        Args:
            state: 현재 워크플로우 상태 (PlanCraftState)
                - analysis: 분석 결과 (필수)
                - rag_context: RAG 컨텍스트 (선택)

        Returns:
            PlanCraftState: 업데이트된 상태
                - structure: 기획서 구조
                - current_step: "structure"
        """
        # =====================================================================
        # 1. 입력 데이터 추출 (객체 접근)
        # =====================================================================
        analysis = state.analysis
        # Pydantic 객체의 정보를 활용하기 위해 model_dump() 호출 (프롬프트 주입용)
        # 단, analysis가 None일 경우를 대비
        analysis_dict = analysis.model_dump() if analysis else {}
        context = state.rag_context
        
        # [개선] refine_count에 따른 형식 확장 로직
        refine_count = getattr(state, "refine_count", 0)
        extension_instruction = ""
        
        if refine_count >= 1:
            extension_instruction += """

---
## [중요] 확장 설계 지시 (개선 단계)
사용자가 더 깊이 있는 기획서를 원합니다. 기존 9개 섹션에 더해, 다음 심화 섹션들을 **반드시 추가**하여 구조를 확장하세요:

10. **상세 기능 명세 (User Flow)**
    - 주요 기능의 화면 흐름 및 사용자 인터랙션 로직 상세화
11. **데이터 구조 및 ERD 설계**
    - 핵심 데이터 엔티티(User, Post, Order 등)와 관계 정의
"""
        if refine_count >= 2:
            extension_instruction += """
12. **마케팅 및 GTM(Go-to-Market) 전략**
    - 초기 사용자 1,000명 확보 전략 및 채널별 마케팅 계획
13. **운영 및 유지보수 계획**
    - CS 대응 프로세스, 서버 모니터링, 장애 대응 체계
"""
        if refine_count >= 3:
            extension_instruction += """
14. **글로벌 진출 및 확장 전략**
    - 다국어 지원, 현지화(L10n) 계획, 국가별 법적 규제 검토
15. **투자 유치(IR) 및 재무 계획**
    - 3개년 손익분기점(BEP) 달성 로드맵, 자금 소요 계획
"""

        # [추가] 사용자 커스텀 요청 처리 지시 (중복 방지 통합)
        user_input = state.user_input
        custom_instruction = f"""

---
## [필수] 사용자 원본 요청 반영 및 중복 방지
사용자의 **원본 요청**을 검토하여, 특정 내용 추가 요구가 있다면 아래 원칙에 따라 처리하세요.

**사용자 원본 요청:**
"{user_input}"

**처리 원칙:**
1. **통합 우선 (Integration First)**: 요청 내용이 '프로젝트 개요', '비즈니스 모델' 등 기존/확장 섹션의 주제와 연관된다면, **새 섹션을 만들지 말고 해당 섹션의 `key_points`에 세부 내용으로 통합**하세요.
   - 예: "가격표 넣어줘" -> '비즈니스 모델' 섹션에 포함.
2. **신규 생성 (New Section)**: 기존 섹션 범주에 포함되지 않는 완전히 독자적인 주제인 경우에만, 적절한 위치(논리적 마지막 순서)에 **새로운 커스텀 섹션을 추가**하세요.
   - 예: "창업 스토리 넣어줘" -> '16. 창업 스토리' 섹션 신설.
"""

        # =====================================================================
        # 2. Structured Output으로 LLM 호출
        # =====================================================================
        # 기본 프롬프트 포맷팅
        user_content = STRUCTURER_USER_PROMPT.format(
            analysis=json.dumps(analysis_dict, ensure_ascii=False, indent=2),
            context=context if context else "없음"
        )
        
        # 확장 지시사항 추가
        if extension_instruction:
            user_content += extension_instruction
            
        # 커스텀 처리 지시사항 추가
        user_content += custom_instruction

        # [NEW] 시계열 기준 주입
        execution_time = getattr(state, "execution_time", None) or "Unknown"
        system_prompt_with_time = (
            f"Current System Time: {execution_time}\n"
            "NOTE: All schedules and milestones MUST be based on this current date.\n\n"
            f"{STRUCTURER_SYSTEM_PROMPT}"
        )

        messages = [
            {"role": "system", "content": system_prompt_with_time},
            {"role": "user", "content": user_content}
        ]

        try:
            # Pydantic 객체 반환
            structure: StructureResult = self.llm.invoke(messages)
            
        except Exception as e:
            # 실패 시 안전한 기본 구조 객체 생성
            from utils.schemas import SectionStructure # Import 필요 시 상단 이동 권장하지만 여기선 간략히
            
            topic = analysis.topic if analysis else "기획서"
            
            structure = StructureResult(
                title=topic,
                sections=[
                    SectionStructure(id=1, name="프로젝트 개요", description="프로젝트 요약", key_points=[]),
                    SectionStructure(id=2, name="배경 및 필요성", description="문제 정의", key_points=[]),
                    SectionStructure(id=3, name="목표", description="기대 효과", key_points=[]),
                    SectionStructure(id=4, name="주요 기능", description="핵심 기능", key_points=[]),
                    SectionStructure(id=5, name="기대 효과", description="가치 창출", key_points=[])
                ]
            )
            state.error = f"구조 설계 오류: {str(e)}"

        # =====================================================================
        # 3. 상태 업데이트 (Pydantic 모델 복사)
        # =====================================================================
        new_state = state.model_copy(update={
            "structure": structure,
            "current_step": "structure"
        })

        return new_state


def run(state: PlanCraftState) -> PlanCraftState:
    """LangGraph 노드용 함수"""
    agent = StructurerAgent()
    return agent.run(state)
