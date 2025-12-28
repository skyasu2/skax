"""
PlanCraft Agent - Writer Agent
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import DraftResult
from graph.state import PlanCraftState, update_state
from prompts.writer_prompt import WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT

# LLM 초기화
writer_llm = get_llm().with_structured_output(DraftResult)

def run(state: PlanCraftState) -> PlanCraftState:
    """
    초안 작성 에이전트 실행
    """
    # 1. 입력 데이터 준비 (Dict Access)
    user_input = state.get("user_input", "")
    structure = state.get("structure")
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    
    if not structure:
        return update_state(state, error="구조화 데이터가 없습니다.")
    
    # Structure 정보 추출
    if isinstance(structure, dict):
        title = structure.get("title", "")
        sections = structure.get("sections", [])
    else:
        title = getattr(structure, "title", "")
        sections = getattr(structure, "sections", [])

    # Refinement Context
    previous_plan_context = ""
    refine_count = state.get("refine_count", 0)
    previous_plan = state.get("previous_plan")
    
    if refine_count > 0 and previous_plan:
        previous_plan_context = f"\n<previous_version>\n{previous_plan}\n</previous_version>\n\n위 이전 버전을 참고하여 더 나은 내용으로 개선하세요."

    # 2. 프롬프트 구성
    messages = [
        {"role": "system", "content": WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": WRITER_USER_PROMPT.format(
            title=title,
            sections=sections,
            user_input=user_input,
            context=f"{rag_context}\n{web_context}",
            previous_plan_context=previous_plan_context
        )}
    ]
    
    # 3. LLM 호출
    try:
        draft_result = writer_llm.invoke(messages)
        
        # 4. 상태 업데이트
        if hasattr(draft_result, "model_dump"):
            draft_dict = draft_result.model_dump()
        else:
            draft_dict = draft_result
            
        return update_state(
            state,
            draft=draft_dict,
            current_step="write"
        )
        
    except Exception as e:
        print(f"[ERROR] Writer Failed: {e}")
        return update_state(state, error=str(e))
