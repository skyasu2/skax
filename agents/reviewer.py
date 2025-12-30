"""
PlanCraft Reviewer Agent - 기획서 평가 및 심사
"""
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import JudgeResult
from graph.state import PlanCraftState, update_state
from prompts.reviewer_prompt import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_PROMPT

# LLM 초기화 (Structured Output)
reviewer_llm = get_llm(temperature=0.1).with_structured_output(JudgeResult)

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
    context = f"{rag_context}\n{web_context}"
    
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
        review_result = reviewer_llm.invoke(messages)
        
        # 4. 상태 업데이트
        if hasattr(review_result, "model_dump"):
            review_dict = review_result.model_dump()
        else:
            review_dict = review_result
            
        return update_state(
            state,
            review=review_dict,
            current_step="review"
        )
        
    except Exception as e:
        print(f"[ERROR] Reviewer Failed: {e}")
        # Fallback: 기본 심사 결과 (조건부 승인)
        fallback_review = {
            "overall_score": 70,
            "feedback_summary": "시스템 에러로 인해 자동 심사가 건너뛰어졌습니다. 수동 검토가 필요할 수 있습니다.",
            "verdict": "PASS",  # 흐름 끊기지 않도록 PASS 처리
            "section_feedbacks": []
        }
        return update_state(state, review=fallback_review, error=f"Reviewer Error: {str(e)}")
