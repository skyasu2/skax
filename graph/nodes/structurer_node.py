"""
Structurer Node
"""
from agents.structurer import run
from graph.state import PlanCraftState
from graph.nodes.common import update_step_history
from utils.tracing import trace_node
from utils.error_handler import handle_node_error
from utils.decorators import require_state_keys

@trace_node("structure")
@require_state_keys(["analysis"])
@handle_node_error
def run_structurer_node(state: PlanCraftState) -> PlanCraftState:
    """
    구조화 Agent 실행 노드

    Side-Effect: LLM 호출 (Azure OpenAI)
    - 기획서 목차/섹션 구조 설계
    - 재시도 안전: 구조만 생성, 외부 상태 변경 없음

    LangSmith: run_name="🏗️ 구조 설계", tags=["agent", "llm", "planning"]
    """
    import time
    start_time = time.time()
    
    new_state = run(state)
    structure = new_state.get("structure")
    count = 0
    if structure:
        from graph.state import ensure_dict
        structure_dict = ensure_dict(structure)
        sections = structure_dict.get("sections", [])
        count = len(sections) if sections else 0
    
    return update_step_history(
        new_state, 
        "structure", 
        "SUCCESS", 
        summary=f"섹션 {count}개 구조화",
        start_time=start_time
    )
