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
        draft = state.draft
        context = state.rag_context

        # draft를 문자열로 변환
        # draft가 None인 경우를 대비해 빈 DraftResult 처리 가능하도록 구현되어야 함
        # 현재는 draft가 Pydantic Optional[DraftResult] 타입
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
            # Pydantic 객체 그대로 사용
            review: JudgeResult = self.llm.invoke(messages)

            # verdict 유효성 검사 (Pydantic Field Validator 권장하지만, 간단히 처리)
            if review.verdict not in ["PASS", "REVISE", "FAIL"]:
                review.verdict = self._infer_verdict(review.overall_score)

        except Exception as e:
            # 실패 시 안전한 기본값 객체 생성
            fallback_review = JudgeResult(
                overall_score=7,
                verdict="REVISE",
                critical_issues=[],
                strengths=["기본 구조가 갖춰져 있습니다"],
                weaknesses=["구체성 보완 필요"],
                action_items=["구체적인 수치와 데이터 추가 필요"],
                reasoning="심사 중 오류 발생으로 기본 REVISE 판정"
            )
            review = fallback_review
            state.error = f"심사 오류: {str(e)}"

        # =====================================================================
        # 3. 상태 업데이트 (Pydantic 모델 복사)
        # =====================================================================
        new_state = state.model_copy(update={
            "review": review,
            "current_step": "review"
        })

        return new_state

    def _format_draft(self, draft: object) -> str: # Type hint: DraftResult (circular import 방지 위해 object 또는 Any)
        """
        draft 객체를 읽기 쉬운 문자열로 변환합니다.

        Args:
            draft: 초안 객체 (DraftResult)

        Returns:
            str: 포맷된 문자열
        """
        if not draft:
            return ""
            
        lines = []
        # Pydantic 객체 접근
        for section in draft.sections:
            lines.append(f"## {section.name}")
            lines.append(section.content)
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
