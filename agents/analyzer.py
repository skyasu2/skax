"""
PlanCraft Agent - Analyzer Agent
"""
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import AnalysisResult
from utils.time_context import get_time_context, get_time_instruction
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
    review_data = state.get("review")
    review_context = "없음"

    if review_data:
        # review_data 형식: {"overall_score": int, "feedback_summary": str, "verdict": str}
        feedback_summary = review_data.get("feedback_summary", "구체적 피드백 없음")
        score = review_data.get("overall_score", 0)
        review_context = (
            f"=== 🚨 이전 버전에 대한 긴급 피드백 (필수 반영) ===\n"
            f"평가 점수: {score}점\n"
            f"지적 사항: {feedback_summary}\n"
            f"지시: 분석 단계에서부터 위 지적 사항을 근본적으로 해결할 수 있는 방안을 제시하세요."
        )
    
    context_parts = []
    if web_context:
        context_parts.append(f"[웹에서 가져온 정보]\n{web_context}")
    if rag_context:
        context_parts.append(f"[기획서 작성 가이드]\n{rag_context}")
    context = "\n\n".join(context_parts) if context_parts else "없음"
    
    # 3. 프롬프트 구성 (시간 컨텍스트 주입)
    system_msg_content = get_time_context() + ANALYZER_SYSTEM_PROMPT

    # [FIX] 프롬프트 템플릿의 {review_data} 인자 전달
    user_msg_content = ANALYZER_USER_PROMPT.format(
        user_input=user_input,
        previous_plan=previous_plan if previous_plan else "없음",
        context=context,
        review_data=review_context
    ) + get_time_instruction()

    messages = [
        {"role": "system", "content": system_msg_content},
        {"role": "user", "content": user_msg_content}
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
