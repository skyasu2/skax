"""
Utility Nodes for PlanCraft
"""
from graph.state import PlanCraftState, update_state
from graph.nodes.common import update_step_history

def general_response_node(state: PlanCraftState) -> PlanCraftState:
    """일반 질의 응답 노드"""
    
    answer = "일반 질의에 대한 응답입니다."
    analysis = state.get("analysis")
    
    if analysis:
         if isinstance(analysis, dict):
             answer = analysis.get("general_answer", answer)
         else:
             answer = getattr(analysis, "general_answer", answer)
    
    new_state = update_state(
        state,
        current_step="general_response",
        final_output=answer
    )
    
    return update_step_history(
        new_state,
        "general_response",
        "SUCCESS",
        summary="일반 질의 응답 완료"
    )
