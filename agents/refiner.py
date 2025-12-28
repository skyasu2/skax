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
        # 1. 입력 데이터 추출 (객체 접근)
        # =====================================================================
        draft = state.draft
        review = state.review
        analysis = state.analysis

        # Pydantic 객체 필드 접근
        score = review.overall_score if review else 7
        verdict = review.verdict if review else "REVISE"
        critical_issues = review.critical_issues if review else []
        action_items = review.action_items if review else []

        # =====================================================================
        # [수정] 참고 자료 섹션 보존 로직 (Immutable Reference)
        # WriterAgent가 생성한 '참고 자료' 섹션을 LLM이 건드리지 않도록 분리합니다.
        # =====================================================================
        ref_section_content = ""
        main_sections = []
        
        if draft and draft.sections:
            for section in draft.sections:
                if "참고 자료" in section.name or "참고문헌" in section.name:
                    ref_section_content = f"\n\n## {section.name}\n\n{section.content}"
                else:
                    main_sections.append(section)

        # =====================================================================
        # 2. PASS 판정 처리 (수정 최소화)
        # =====================================================================
        if verdict == "PASS" and score >= 9 and not action_items:
            final_md = self._format_draft_only(draft)
            
            new_state = state.model_copy(update={
                "final_output": final_md,
                "refined": False,
                "current_step": "refine"
            })
            return new_state

        # =====================================================================
        # 3. draft 문자열 변환 (참고 자료 제외)
        # =====================================================================
        # LLM에게는 참고 자료를 제외한 본문만 전달하여 수정을 요청합니다.
        draft_str = ""
        for section in main_sections:
            draft_str += f"## {section.name}\n{section.content}\n\n"

        # =====================================================================
        # 4. verdict별 지시사항 선택
        # =====================================================================
        verdict_instruction = VERDICT_INSTRUCTIONS.get(verdict, VERDICT_INSTRUCTIONS["REVISE"])

        # =====================================================================
        # 5. 프롬프트 구성 및 LLM 호출
        # =====================================================================
        # analysis는 Optional[AnalysisResult]이므로 None 체크 필요
        topic = analysis.topic if analysis else ""
        purpose = analysis.purpose if analysis else ""
        target_users = analysis.target_users if analysis else ""
        key_features = ", ".join(analysis.key_features) if analysis else ""

        messages = [
            {"role": "system", "content": REFINER_SYSTEM_PROMPT},
            {"role": "user", "content": REFINER_USER_PROMPT.format(
                draft=draft_str,
                score=score,
                verdict=verdict,
                critical_issues="\n".join(f"- {c}" for c in critical_issues) if critical_issues else "없음",
                action_items="\n".join(f"- {a}" for a in action_items) if action_items else "없음",
                topic=topic,
                purpose=purpose,
                target_users=target_users,
                key_features=key_features,
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
            
            # [수정] 보존해둔 참고 자료 섹션 다시 붙이기
            if ref_section_content:
                refined_output += ref_section_content

        except Exception as e:
            # 실패 시 원본 draft 사용
            refined_output = self._format_draft_only(draft)
            state.error = f"개선 작업 오류: {str(e)}"

        # =====================================================================
        # 6. 상태 업데이트 (Pydantic 모델 복사)
        # =====================================================================
        new_state = state.model_copy(update={
            "final_output": refined_output,
            "refined": True,
            "current_step": "refine"
        })

        return new_state

    def _format_draft(self, draft: object) -> str: # Type hint: DraftResult
        """draft 객체를 읽기 쉬운 문자열로 변환"""
        if not draft:
            return ""
        lines = []
        for section in draft.sections:
            lines.append(f"## {section.name}")
            lines.append(section.content)
            lines.append("")
        return "\n".join(lines)

    def _format_draft_only(self, draft: object) -> str: # Type hint: DraftResult
        """draft 객체를 기획서 형식으로 변환 (심사 결과 제외)"""
        if not draft:
            return ""
        lines = ["# 기획서\n"]
        for section in draft.sections:
            lines.append(f"## {section.name}")
            lines.append(section.content)
            lines.append("")
        return "\n".join(lines)


def run(state: PlanCraftState) -> PlanCraftState:
    """
    기획서 개선 에이전트 실행
    
    심사 결과(ReviewResult)를 바탕으로 개선 여부를 판단하고,
    필요 시 다시 구조화/작성 단계로 라우팅하기 위한 메타데이터를 업데이트합니다.
    """
    from graph.state import update_state

    # 1. 입력 데이터 준비
    review = state.get("review")
    if not review:
        return update_state(state, error="심사 결과가 없습니다.")
        
    # Review 내용 추출
    if isinstance(review, dict):
        verdict = review.get("verdict", "FAIL")
    else:
        verdict = getattr(review, "verdict", "FAIL")
    
    current_count = state.get("refine_count", 0)
    
    # 2. 개선 로직 수행 (간소화)
    # 실제로는 여기서 뭔가 더 복잡한 판단을 할 수 있음
    
    # PASS가 아니면 개선 카운트 증가 및 이전 계획 저장
    if verdict != "PASS" and current_count < 3:
        # 현재 Draft를 Previous Plan으로 저장
        draft = state.get("draft")
        previous_text = ""
        if draft:
            sections = draft.get("sections") if isinstance(draft, dict) else getattr(draft, "sections", [])
            previous_text = "\n\n".join([f"## {s.get('name', '')}\n{s.get('content', '')}" if isinstance(s, dict) else f"## {s.name}\n{s.content}" for s in sections])
            
        print(f"[Refiner] 개선 필요 (Verdict: {verdict}, Round: {current_count + 1})")
        
        # 순환 참조 방지: draft, structure 등을 초기화하지 않고 그대로 둠 (Writer가 참고함)
        # 단, refine_count는 증가
        return update_state(
            state,
            refine_count=current_count + 1,
            previous_plan=previous_text,
            current_step="refine",
            refined=True
        )
    else:
        print("[Refiner] 통과 또는 최대 재시도 도달")
        return update_state(
            state,
            current_step="refine",
            refined=False # 더 이상 개선 안함
        )
