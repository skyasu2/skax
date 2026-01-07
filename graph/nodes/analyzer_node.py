"""
Analyzer Node
"""
from agents.analyzer import run
from graph.state import PlanCraftState, update_state
from graph.nodes.common import update_step_history
from utils.tracing import trace_node
from utils.error_handler import handle_node_error

@trace_node("analyze", tags=["critical"])
@handle_node_error
def run_analyzer_node(state: PlanCraftState) -> PlanCraftState:
    """
    분석 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)
    - 멱등성: 동일 입력에 유사한 결과 (LLM 특성상 약간의 변동 있음)
    - 재시도 안전: 상태 변경 없이 분석 결과만 반환

    LangSmith 트레이싱:
        - run_name: "🔍 요구사항 분석"
        - tags: ["agent", "llm", "analysis", "critical"]
    """
    import time
    start_time = time.time()
    
    # [PHASE 1] Reviewer에서 복귀한 경우 restart_count 증가
    current_restart_count = state.get("restart_count", 0)
    has_review = state.get("review") is not None
    
    if has_review:
        # Reviewer를 거친 후 다시 Analyzer로 온 경우 = 재분석
        current_restart_count += 1
        print(f"[ROUTING] Analyzer 재진입 (restart_count: {current_restart_count})")
    
    new_state = run(state)
    
    # restart_count 업데이트
    new_state = update_state(new_state, restart_count=current_restart_count)
    
    analysis = new_state.get("analysis")
    topic = "N/A"
    if analysis:
        from graph.state import ensure_dict
        analysis_dict = ensure_dict(analysis)
        topic = analysis_dict.get("topic", "N/A")
    
    return update_step_history(
        new_state, 
        "analyze", 
        "SUCCESS", 
        summary=f"주제 분석: {topic}" + (f" (재분석 #{current_restart_count})" if has_review else ""),
        start_time=start_time
    )
