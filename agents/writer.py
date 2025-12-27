"""
PlanCraft Agent - Writer Agent

설계된 구조에 따라 기획서 내용을 작성하는 Agent입니다.
각 섹션별로 구체적이고 전문적인 내용을 생성합니다.

주요 기능:
    - 섹션별 내용 작성
    - 마크다운 형식 출력
    - 개조식/넘버링 활용
    - 구체적 수치 제시

입력:
    - user_input: 원본 사용자 입력
    - structure: 기획서 구조
    - rag_context: RAG 검색 결과 (선택)

출력:
    - draft: 초안 딕셔너리

Best Practice 적용:
    - with_structured_output(): LangChain 표준 Structured Output 패턴
    - PlanCraftState 타입 어노테이션: 명시적 입출력 타입
"""

import json
from utils.llm import get_llm
from utils.schemas import DraftResult
from graph.state import PlanCraftState
from prompts.writer_prompt import WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT


class WriterAgent:
    """
    기획서 내용을 작성하는 Agent

    LangChain의 with_structured_output()을 사용하여
    Pydantic 스키마 기반의 구조화된 출력을 생성합니다.

    Attributes:
        llm: AzureChatOpenAI 인스턴스 (Structured Output 적용)
    """

    def __init__(self, model_type: str = "gpt-4o"):
        """
        Writer Agent를 초기화합니다.

        Args:
            model_type: 사용할 LLM 모델
        """
        # 작성은 창의성이 필요하므로 높은 temperature 사용
        base_llm = get_llm(model_type=model_type, temperature=0.7)

        # with_structured_output: LangChain Best Practice
        self.llm = base_llm.with_structured_output(DraftResult)

    def run(self, state: PlanCraftState) -> PlanCraftState:
        """
        기획서 내용을 작성합니다.

        Args:
            state: 현재 워크플로우 상태 (PlanCraftState)
                - user_input: 원본 입력
                - structure: 기획서 구조 (필수)
                - rag_context: RAG 컨텍스트 (선택)

        Returns:
            PlanCraftState: 업데이트된 상태
                - draft: 작성된 초안
                - current_step: "write"
        """
        # =====================================================================
        # 1. 입력 데이터 추출
        # =====================================================================
        user_input = state.get("user_input", "")
        structure = state.get("structure", {})
        context = state.get("rag_context", "")

        # =====================================================================
        # 2. Structured Output으로 LLM 호출
        # =====================================================================
        messages = [
            {"role": "system", "content": WRITER_SYSTEM_PROMPT},
            {"role": "user", "content": WRITER_USER_PROMPT.format(
                user_input=user_input,
                structure=json.dumps(structure, ensure_ascii=False, indent=2),
                context=context if context else "없음"
            )}
        ]

        try:
            # with_structured_output 사용: 자동으로 Pydantic 객체 반환
            draft: DraftResult = self.llm.invoke(messages)
            draft_dict = draft.model_dump()

        except Exception as e:
            # 실패 시 기본 초안 반환
            draft_dict = {
                "sections": [
                    {"id": 1, "name": "초안", "content": "내용 작성 중 오류 발생"}
                ]
            }
            state["error"] = f"초안 작성 오류: {str(e)}"

        # =====================================================================
        # 3. 상태 업데이트
        # =====================================================================
        state["draft"] = draft_dict
        state["current_step"] = "write"

        return state

    def format_as_markdown(self, draft: dict) -> str:
        """
        draft를 마크다운 형식으로 변환합니다.

        Args:
            draft: 초안 딕셔너리

        Returns:
            str: 마크다운 형식 문자열
        """
        md_content = []

        for section in draft.get("sections", []):
            md_content.append(f"## {section.get('name', '')}")
            md_content.append("")
            md_content.append(section.get("content", ""))
            md_content.append("")

        return "\n".join(md_content)


def run(state: PlanCraftState) -> PlanCraftState:
    """LangGraph 노드용 함수"""
    agent = WriterAgent()
    return agent.run(state)
