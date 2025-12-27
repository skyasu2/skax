"""
PlanCraft Agent - Reviewer(Judge) Agent

작성된 기획서를 냉정하게 심사하고 PASS/REVISE/FAIL 판정을 내립니다.
이 판정은 Refiner가 적절한 수준의 개선을 하도록 가이드합니다.

주요 기능:
    - 치명적 문제 검사 (BM, MVP, 논리성)
    - PASS/REVISE/FAIL 판정
    - 구체적인 action_items 도출

입력:
    - draft: Writer Agent의 초안
    - rag_context: RAG 검색 결과 (선택)

출력:
    - review: 심사 결과 딕셔너리 (verdict, action_items 포함)

Best Practice 적용:
    - with_structured_output(): LangChain 표준 Structured Output 패턴
    - PlanCraftState 타입 어노테이션: 명시적 입출력 타입
"""

from utils.llm import get_llm
from utils.schemas import JudgeResult
from graph.state import PlanCraftState
from prompts.reviewer_prompt import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_PROMPT


class ReviewerAgent:
    """
    기획서를 냉정하게 심사하는 Judge Agent

    LangChain의 with_structured_output()을 사용하여
    PASS/REVISE/FAIL 판정과 구체적인 action_items를 제공합니다.

    Attributes:
        llm: AzureChatOpenAI 인스턴스 (Structured Output 적용)
    """

    def __init__(self, model_type: str = "gpt-4o"):
        """
        Reviewer(Judge) Agent를 초기화합니다.

        Args:
            model_type: 사용할 LLM 모델
        """
        # 심사는 일관성과 엄격함이 중요하므로 낮은 temperature 사용
        base_llm = get_llm(model_type=model_type, temperature=0.2)

        # with_structured_output: LangChain Best Practice
        self.llm = base_llm.with_structured_output(JudgeResult)

    def run(self, state: PlanCraftState) -> PlanCraftState:
        """
        기획서를 심사합니다.

        Args:
            state: 현재 워크플로우 상태 (PlanCraftState)
                - draft: 초안 (필수)
                - rag_context: RAG 컨텍스트 (선택)

        Returns:
            PlanCraftState: 업데이트된 상태
                - review: 심사 결과 (verdict, action_items 포함)
                - current_step: "review"
        """
        # =====================================================================
        # 1. 입력 데이터 추출
        # =====================================================================
        draft = state.get("draft", {})
        context = state.get("rag_context", "")

        # draft를 문자열로 변환
        draft_str = self._format_draft(draft)

        # =====================================================================
        # 2. Structured Output으로 LLM 호출
        # =====================================================================
        messages = [
            {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
            {"role": "user", "content": REVIEWER_USER_PROMPT.format(
                draft=draft_str,
                context=context if context else "없음"
            )}
        ]

        try:
            # with_structured_output 사용: 자동으로 Pydantic 객체 반환
            review: JudgeResult = self.llm.invoke(messages)
            review_dict = review.model_dump()

            # verdict 유효성 검사 (Pydantic이 처리하지 못한 경우 대비)
            if review_dict.get("verdict") not in ["PASS", "REVISE", "FAIL"]:
                review_dict["verdict"] = self._infer_verdict(review_dict.get("overall_score", 7))

        except Exception as e:
            # 파싱 실패 시 기본 REVISE 판정 반환
            review_dict = {
                "overall_score": 7,
                "verdict": "REVISE",
                "critical_issues": [],
                "strengths": ["기본 구조가 갖춰져 있습니다"],
                "weaknesses": ["구체성 보완 필요"],
                "action_items": ["구체적인 수치와 데이터 추가 필요"],
                "reasoning": "심사 중 오류 발생으로 기본 REVISE 판정"
            }
            state["error"] = f"심사 오류: {str(e)}"

        # =====================================================================
        # 3. 상태 업데이트
        # =====================================================================
        state["review"] = review_dict
        state["current_step"] = "review"

        # NOTE: final_output은 Refiner Agent에서 생성합니다.
        # Reviewer는 판정 결과만 저장하고, Refiner가 판정에 따라 개선합니다.

        return state

    def _format_draft(self, draft: dict) -> str:
        """
        draft를 읽기 쉬운 문자열로 변환합니다.

        Args:
            draft: 초안 딕셔너리

        Returns:
            str: 포맷된 문자열
        """
        lines = []
        for section in draft.get("sections", []):
            lines.append(f"## {section.get('name', '')}")
            lines.append(section.get("content", ""))
            lines.append("")
        return "\n".join(lines)

    def _infer_verdict(self, score: int) -> str:
        """
        점수로부터 verdict를 추론합니다.

        Args:
            score: 전체 점수 (1-10)

        Returns:
            str: PASS, REVISE, 또는 FAIL
        """
        if score >= 9:
            return "PASS"
        elif score >= 6:
            return "REVISE"
        else:
            return "FAIL"


def run(state: PlanCraftState) -> PlanCraftState:
    """LangGraph 노드용 함수"""
    agent = ReviewerAgent()
    return agent.run(state)
