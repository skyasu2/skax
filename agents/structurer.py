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
        
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    context = f"{rag_context}\n{web_context}".strip()
    
    # Analysis 내용을 문자열로 변환하여 프롬프트에 주입
    analysis_str = str(analysis)
    
    # 2. 프롬프트 구성
    # 프롬프트 플레이스홀더: {analysis}, {context}
    messages = [
        {"role": "system", "content": STRUCTURER_SYSTEM_PROMPT},
        {"role": "user", "content": STRUCTURER_USER_PROMPT.format(
            analysis=analysis_str,
            context=context if context else "없음"
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
