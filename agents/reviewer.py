"""
PlanCraft Reviewer Agent - 기획서 평가 및 심사
"""
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import JudgeResult
from graph.state import PlanCraftState, update_state, ensure_dict
from prompts.reviewer_prompt import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_PROMPT

# LLM은 함수 내에서 지연 초기화 (환경 변수 로딩 타이밍 이슈 방지)
_reviewer_llm = None

def _get_reviewer_llm():
    """Reviewer LLM 지연 초기화"""
    global _reviewer_llm
    if _reviewer_llm is None:
        _reviewer_llm = get_llm(temperature=0.1).with_structured_output(JudgeResult)
    return _reviewer_llm

def run(state: PlanCraftState) -> PlanCraftState:
    """
    기획서 검토 에이전트 실행
    
    작성된 초안(DraftResult)을 평가하고 개선점을 도출합니다.
    
    Example:
        >>> state = {"draft": {...}}
        >>> result = run(state)
        >>> print(result["review"]["overall_score"])
        85
    """
    
    # 1. 입력 데이터 준비
    draft = state.get("draft")
    if not draft:
        return update_state(state, error="검토할 초안이 없습니다.")
    
    # Draft 내용 추출
    if isinstance(draft, dict):
        sections = draft.get("sections", [])
    else:
        sections = getattr(draft, "sections", [])
        
    full_text = "\n\n".join([f"## {s.get('name', '')}\n{s.get('content', '')}" if isinstance(s, dict) else f"## {s.name}\n{s.content}" for s in sections])
    
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    
    # [NEW] 전문 에이전트 분석 결과를 컨텍스트에 추가 (교차 검증용)
    specialist_analysis = state.get("specialist_analysis", {})
    specialist_context = specialist_analysis.get("integrated_context", "") if isinstance(specialist_analysis, dict) else ""
    
    context = f"{rag_context}\n{web_context}"
    if specialist_context:
        context += f"\n\n=== [전문 에이전트 분석 결과 (Fact Check 기준)] ===\n{specialist_context}"
    
    # 2. 프롬프트 구성
    # REVIEWER_USER_PROMPT는 {draft}, {context}를 요구함
    
    messages = [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {"role": "user", "content": REVIEWER_USER_PROMPT.format(
            draft=full_text,
            context=context if context.strip() else "없음"
        )}
    ]
    
    # 3. LLM 호출
    try:
        review_result = _get_reviewer_llm().invoke(messages)
        
        # 4. 상태 업데이트 (Pydantic -> Dict 일관성 보장)
        review_dict = ensure_dict(review_result)
            
        return update_state(
            state,
            review=review_dict,
            current_step="review"
        )
        
    except Exception as e:
        print(f"[ERROR] Reviewer Failed: {e}")
        # Fallback: 기본 심사 결과 (REVISE로 설정하여 Refiner가 보완하도록 함)
        fallback_review = {
            "overall_score": 7,  # 7점 = REVISE 범위 (5-8점)
            "feedback_summary": "시스템 에러로 인해 자동 심사가 건너뛰어졌습니다. Refiner가 기본 검토를 수행합니다.",
            "verdict": "REVISE",  # 점수와 일치하도록 REVISE 설정
            "critical_issues": [],
            "strengths": [],
            "weaknesses": ["자동 심사 실패로 인한 기본값 적용"],
            "action_items": ["전반적인 내용 검토 필요"]
        }
        return update_state(state, review=fallback_review, error=f"Reviewer Error: {str(e)}")
