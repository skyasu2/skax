"""
PlanCraft Agent - Refiner Agent

Judge의 판정(PASS/REVISE/FAIL)에 따라 차별화된 개선을 수행합니다.
- PASS: 수정 없이 통과 (오타 수정 수준)
- REVISE: action_items 반영하여 개선
- FAIL: 전면 재설계

핵심 원칙:
- 사용자에게는 항상 완성된 기획서만 제공
- 내부 판정/점수는 노출하지 않음

입력:
    - draft: Writer의 초안
    - review: Judge의 심사 결과 (verdict, action_items 포함)
    - analysis: Analyzer의 분석 결과

출력:
    - final_output: 완성된 기획서 (마크다운)
    - refined: 개선 작업 수행 여부

Best Practice 적용:
    - PlanCraftState 타입 어노테이션: 명시적 입출력 타입
    - NOTE: Refiner는 자유형식 마크다운을 출력하므로 Structured Output 미적용
"""

from utils.llm import get_llm
from graph.state import PlanCraftState
from prompts.refiner_prompt import (
    REFINER_SYSTEM_PROMPT,
    REFINER_USER_PROMPT,
    VERDICT_INSTRUCTIONS
)


class RefinerAgent:
    """
    Judge 판정에 따라 기획서를 완성하는 Agent

    판정별로 다른 수준의 개선을 수행합니다:
    - PASS: 미세 조정
    - REVISE: action_items 반영
    - FAIL: 전면 재설계

    NOTE: Refiner는 자유형식 마크다운을 출력하므로 with_structured_output() 미적용

    Attributes:
        llm: AzureChatOpenAI 인스턴스
    """

    def __init__(self, model_type: str = "gpt-4o"):
        """
        Refiner Agent를 초기화합니다.

        Args:
            model_type: 사용할 LLM 모델
        """
        self.llm = get_llm(model_type=model_type, temperature=0.5)

    def run(self, state: PlanCraftState) -> PlanCraftState:
        """
        기획서를 완성합니다.

        Args:
            state: 현재 워크플로우 상태 (PlanCraftState)
                - draft: 초안 (필수)
                - review: Judge 심사 결과 (필수)
                - analysis: 분석 결과 (선택)

        Returns:
            PlanCraftState: 업데이트된 상태
                - final_output: 완성된 기획서
                - refined: 개선 작업 수행 여부
                - current_step: "refine"
        """
        # =====================================================================
        # 1. 입력 데이터 추출
        # =====================================================================
        draft = state.get("draft", {})
        review = state.get("review", {})
        analysis = state.get("analysis", {})

        score = review.get("overall_score", 7)
        verdict = review.get("verdict", "REVISE")
        critical_issues = review.get("critical_issues", [])
        action_items = review.get("action_items", [])

        # =====================================================================
        # 2. PASS 판정 처리 (수정 최소화)
        # =====================================================================
        if verdict == "PASS" and score >= 9 and not action_items:
            state["final_output"] = self._format_draft_only(draft)
            state["refined"] = False
            state["current_step"] = "refine"
            return state

        # =====================================================================
        # 3. draft 문자열 변환
        # =====================================================================
        draft_str = self._format_draft(draft)

        # =====================================================================
        # 4. verdict별 지시사항 선택
        # =====================================================================
        verdict_instruction = VERDICT_INSTRUCTIONS.get(verdict, VERDICT_INSTRUCTIONS["REVISE"])

        # =====================================================================
        # 5. 프롬프트 구성 및 LLM 호출
        # =====================================================================
        messages = [
            {"role": "system", "content": REFINER_SYSTEM_PROMPT},
            {"role": "user", "content": REFINER_USER_PROMPT.format(
                draft=draft_str,
                score=score,
                verdict=verdict,
                critical_issues="\n".join(f"- {c}" for c in critical_issues) if critical_issues else "없음",
                action_items="\n".join(f"- {a}" for a in action_items) if action_items else "없음",
                topic=analysis.get("topic", ""),
                purpose=analysis.get("purpose", ""),
                target_users=analysis.get("target_users", ""),
                key_features=", ".join(analysis.get("key_features", [])),
                verdict_instruction=verdict_instruction
            )}
        ]

        try:
            response = self.llm.invoke(messages)
            refined_output = response.content

            # 마크다운 블록 제거 (있다면)
            if refined_output.startswith("```markdown"):
                refined_output = refined_output[11:]
            if refined_output.startswith("```"):
                refined_output = refined_output[3:]
            if refined_output.endswith("```"):
                refined_output = refined_output[:-3]

            refined_output = refined_output.strip()

        except Exception as e:
            # 실패 시 원본 draft 사용
            refined_output = self._format_draft_only(draft)
            state["error"] = f"개선 작업 오류: {str(e)}"

        # =====================================================================
        # 6. 상태 업데이트
        # =====================================================================
        state["final_output"] = refined_output
        state["refined"] = True
        state["current_step"] = "refine"

        return state

    def _format_draft(self, draft: dict) -> str:
        """draft를 읽기 쉬운 문자열로 변환"""
        lines = []
        for section in draft.get("sections", []):
            lines.append(f"## {section.get('name', '')}")
            lines.append(section.get("content", ""))
            lines.append("")
        return "\n".join(lines)

    def _format_draft_only(self, draft: dict) -> str:
        """draft를 기획서 형식으로 변환 (심사 결과 제외)"""
        lines = ["# 기획서\n"]
        for section in draft.get("sections", []):
            lines.append(f"## {section.get('name', '')}")
            lines.append(section.get("content", ""))
            lines.append("")
        return "\n".join(lines)


def run(state: PlanCraftState) -> PlanCraftState:
    """LangGraph 노드용 함수"""
    agent = RefinerAgent()
    return agent.run(state)
