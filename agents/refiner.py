
"""
PlanCraft Agent - Refiner Agent
"""
from utils.llm import get_llm
from graph.state import PlanCraftState, update_state, ensure_dict
from utils.schemas import RefinementStrategy
from prompts.refiner_prompt import REFINER_SYSTEM_PROMPT, REFINER_USER_PROMPT
from utils.file_logger import get_file_logger

def run(state: PlanCraftState) -> PlanCraftState:
    """
    기획서 개선 에이전트 실행 (LLM 기반 전략 수립)
    
    심사 결과(ReviewResult)를 바탕으로 개선 전략(RefinementStrategy)을 수립하고,
    Writer가 다음 초안 작성 시 참고할 구체적인 가이드라인을 생성합니다.
    """
    logger = get_file_logger()
    
    # 1. 입력 데이터 준비
    review = state.get("review")
    draft = state.get("draft")
    
    if not review:
        logger.error("[Refiner] 심사 결과 누락")
        return update_state(state, error="심사 결과가 없습니다.")
        
    # Review 데이터 추출
    if isinstance(review, dict):
        verdict = review.get("verdict", "FAIL")
        score = review.get("overall_score", 0)
        feedback = review.get("feedback_summary", "")
        issues = "\n".join([f"- {i}" for i in review.get("critical_issues", [])])
    else:
        verdict = getattr(review, "verdict", "FAIL")
        score = getattr(review, "overall_score", 0)
        feedback = getattr(review, "feedback_summary", "")
        issues = "\n".join([f"- {i}" for i in getattr(review, "critical_issues", [])])
    
    current_count = state.get("refine_count", 0)
    MAX_RETRIES = 3 # 설정 파일 연동 가능
    
    # PASS 또는 횟수 초과 시 -> Stop Refinement
    if verdict == "PASS" or current_count >= MAX_RETRIES:
        logger.info(f"[Refiner] 개선 종료 (Verdict: {verdict}, Round: {current_count})")
        return update_state(
            state,
            current_step="refine",
            refined=False # 더 이상 개선 안함
        )
        
    # 2. 개선 전략 수립 (LLM 호출)
    logger.info(f"[Refiner] 개선 전략 수립 시작 (Round {current_count + 1})")
    
    # Draft 요약 (너무 길면 자름)
    draft_summary = "초안 데이터 없음"
    if draft:
        sections = draft.get("sections") if isinstance(draft, dict) else getattr(draft, "sections", [])
        draft_summary = "\n".join([f"[{s.get('name', 'Unknown')}]\n{s.get('content', '')[:200]}..." if isinstance(s, dict) else f"[{s.name}]\n{s.content[:200]}..." for s in sections])

    # LLM 초기화
    refiner_llm = get_llm(temperature=0.4).with_structured_output(RefinementStrategy)
    
    messages = [
        {"role": "system", "content": REFINER_SYSTEM_PROMPT},
        {"role": "user", "content": REFINER_USER_PROMPT.format(
            verdict=verdict,
            score=score,
            feedback=feedback,
            issues=issues if issues else "(없음)",
            draft_summary=draft_summary
        )}
    ]
    
    strategy_data = None
    try:
        strategy_result = refiner_llm.invoke(messages)
        
        # Pydantic -> Dict 일관성 보장
        strategy_data = ensure_dict(strategy_result)
            
        logger.info(f"[Refiner] 전략 수립 완료: {strategy_data.get('overall_direction')}")
        
    except Exception as e:
        logger.error(f"[Refiner] 전략 수립 실패: {e}")
        # Fallback 전략
        strategy_data = {
            "overall_direction": "심사 피드백을 충실히 반영하여 수정",
            "key_focus_areas": ["지적된 치명적 루프 보완", "논리적 흐름 강화"],
            "specific_guidelines": ["심사관이 언급한 각 항목을 하나씩 검토하여 수정할 것"],
            "additional_search_keywords": []
        }

    # 3. 상태 업데이트
    # 현재 draft를 백업
    previous_text = ""
    if draft:
        sections = draft.get("sections") if isinstance(draft, dict) else getattr(draft, "sections", [])
        previous_text = "\n\n".join([f"## {s.get('name', '')}\n{s.get('content', '')}" if isinstance(s, dict) else f"## {s.name}\n{s.content}" for s in sections])

    return update_state(
        state,
        refine_count=current_count + 1,
        previous_plan=previous_text,
        refinement_guideline=strategy_data, # [NEW] 전략 전달
        current_step="refine",
        refined=True
    )
