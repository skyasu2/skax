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
        # 1. 입력 데이터 추출
        # =====================================================================
        analysis = state.get("analysis", {})
        context = state.get("rag_context", "")

        # =====================================================================
        # 2. Structured Output으로 LLM 호출
        # =====================================================================
        messages = [
            {"role": "system", "content": STRUCTURER_SYSTEM_PROMPT},
            {"role": "user", "content": STRUCTURER_USER_PROMPT.format(
                analysis=json.dumps(analysis, ensure_ascii=False, indent=2),
                context=context if context else "없음"
            )}
        ]

        try:
            # with_structured_output 사용: 자동으로 Pydantic 객체 반환
            structure: StructureResult = self.llm.invoke(messages)
            structure_dict = structure.model_dump()

        except Exception as e:
            # 파싱 실패 시 기본 구조 반환
            fallback_structure = {
                "title": analysis.get("topic", "기획서"),
                "sections": [
                    {"id": 1, "name": "프로젝트 개요", "description": "프로젝트 요약", "key_points": []},
                    {"id": 2, "name": "배경 및 필요성", "description": "문제 정의", "key_points": []},
                    {"id": 3, "name": "목표", "description": "기대 효과", "key_points": []},
                    {"id": 4, "name": "주요 기능", "description": "핵심 기능", "key_points": []},
                    {"id": 5, "name": "기대 효과", "description": "가치 창출", "key_points": []}
                ]
            }
            structure_dict = fallback_structure
            state["error"] = f"구조 설계 오류: {str(e)}"

        # =====================================================================
        # 3. 상태 업데이트
        # =====================================================================
        state.update({
            "structure": structure_dict,
            "current_step": "structure"
        })

        return state


def run(state: PlanCraftState) -> PlanCraftState:
    """LangGraph 노드용 함수"""
    agent = StructurerAgent()
    return agent.run(state)
