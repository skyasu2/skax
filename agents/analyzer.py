"""
PlanCraft Agent - Analyzer Agent
"""
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import AnalysisResult
from graph.state import PlanCraftState, update_state
from prompts.analyzer_prompt import ANALYZER_SYSTEM_PROMPT, ANALYZER_USER_PROMPT

# LLM 초기화
analyzer_llm = get_llm().with_structured_output(AnalysisResult)

def run(state: PlanCraftState) -> PlanCraftState:
    """
    요청 분석 에이전트 실행
    """
    # 1. 입력 데이터 준비 (Dict Access)
    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    previous_plan = state.get("previous_plan")
    
    # 2. 컨텍스트 구성
    context_parts = []
    if web_context:
        context_parts.append(f"[웹에서 가져온 정보]\n{web_context}")
    if rag_context:
        context_parts.append(f"[기획서 작성 가이드]\n{rag_context}")
    context = "\n\n".join(context_parts) if context_parts else "없음"
    
    # 3. 프롬프트 구성
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_msg_content = (
        f"Current System Time: {current_time_str}\n"
        "NOTE: All analysis and reasoning MUST be based on this current time.\n\n"
        f"{ANALYZER_SYSTEM_PROMPT}"
    )

    messages = [
        {"role": "system", "content": system_msg_content},
        {"role": "user", "content": ANALYZER_USER_PROMPT.format(
            user_input=user_input,
            previous_plan=previous_plan if previous_plan else "없음",
            context=context
        )}
    ]
    
    # 4. LLM 호출
    try:
        analysis_result = analyzer_llm.invoke(messages)
        
        # 5. 상태 업데이트
        # Pydantic -> Dict 변환
        if hasattr(analysis_result, "model_dump"):
            analysis_dict = analysis_result.model_dump()
        else:
            analysis_dict = analysis_result

        updates = {
            "analysis": analysis_dict,
            "need_more_info": analysis_dict.get("need_more_info", False),
            "options": analysis_dict.get("options", []),
            "option_question": analysis_dict.get("option_question"),
            "current_step": "analyze"
        }
            
        return update_state(state, **updates)
        
    except Exception as e:
        print(f"[ERROR] Analyzer Failed: {e}")
        return update_state(state, error=str(e))
