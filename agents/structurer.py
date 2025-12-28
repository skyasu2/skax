"""
PlanCraft Agent - Structurer Agent
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import StructureResult
from graph.state import PlanCraftState, update_state
from prompts.structurer_prompt import STRUCTURER_SYSTEM_PROMPT, STRUCTURER_USER_PROMPT

# LLM 초기화
structurer_llm = get_llm().with_structured_output(StructureResult)

def run(state: PlanCraftState) -> PlanCraftState:
    """
    구조화 에이전트 실행
    """
    # 1. 입력 데이터 준비 (Dict Access)
    user_input = state.get("user_input", "")
    analysis = state.get("analysis")
    
    if not analysis:
        return update_state(state, error="분석 데이터가 없습니다.")
        
    topic = analysis.get("topic", "") if isinstance(analysis, dict) else getattr(analysis, "topic", "")
    target_audience = analysis.get("target_audience", "") if isinstance(analysis, dict) else getattr(analysis, "target_audience", "")
    requirements = analysis.get("key_requirements", []) if isinstance(analysis, dict) else getattr(analysis, "key_requirements", [])
    
    # 2. 프롬프트 구성
    messages = [
        {"role": "system", "content": STRUCTURER_SYSTEM_PROMPT},
        {"role": "user", "content": STRUCTURER_USER_PROMPT.format(
            topic=topic,
            target_audience=target_audience,
            requirements=requirements,
            user_input=user_input
        )}
    ]
    
    # 3. LLM 호출
    try:
        structure_result = structurer_llm.invoke(messages)
        
        # 4. 상태 업데이트
        if hasattr(structure_result, "model_dump"):
            structure_dict = structure_result.model_dump()
        else:
            structure_dict = structure_result
            
        return update_state(
            state,
            structure=structure_dict,
            current_step="structure"
        )
        
    except Exception as e:
        print(f"[ERROR] Structurer Failed: {e}")
        return update_state(state, error=str(e))
