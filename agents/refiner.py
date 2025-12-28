"""
PlanCraft Agent - Refiner Agent
"""
from utils.llm import get_llm
from graph.state import PlanCraftState, update_state
# Refiner는 별도의 LLM 호출 없이 Review 결과를 바탕으로 라우팅만 결정함 (Logic-only Agent)
# 하지만 필요하다면 LLM을 사용하여 개선 전략을 수립할 수도 있음.
# 현재 로직에서는 단순 라우팅만 수행하므로 LLM 초기화 생략 가능, 혹은 향후 확장을 위해 import 유지

def run(state: PlanCraftState) -> PlanCraftState:
    """
    기획서 개선 에이전트 실행
    
    심사 결과(ReviewResult)를 바탕으로 개선 여부를 판단하고,
    필요 시 다시 구조화/작성 단계로 라우팅하기 위한 메타데이터를 업데이트합니다.
    """
    
    # 1. 입력 데이터 준비 (Dict Access)
    review = state.get("review")
    if not review:
        return update_state(state, error="심사 결과가 없습니다.")
        
    # Review 내용 추출
    if isinstance(review, dict):
        verdict = review.get("verdict", "FAIL")
    else:
        verdict = getattr(review, "verdict", "FAIL")
    
    current_count = state.get("refine_count", 0)
    
    # 2. 개선 로직 수행
    if verdict != "PASS" and current_count < 3:
        # 현재 Draft를 Previous Plan으로 저장
        draft = state.get("draft")
        previous_text = ""
        if draft:
            sections = draft.get("sections") if isinstance(draft, dict) else getattr(draft, "sections", [])
            previous_text = "\n\n".join([f"## {s.get('name', '')}\n{s.get('content', '')}" if isinstance(s, dict) else f"## {s.name}\n{s.content}" for s in sections])
            
        print(f"[Refiner] 개선 필요 (Verdict: {verdict}, Round: {current_count + 1})")
        
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
