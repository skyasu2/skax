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
    
    # [FIX] 파일 내용 통합 (짧은 입력 대응)
    file_content = state.get("file_content")
    file_context_msg = ""
    
    if file_content:
        # 길이 제한 (토큰 비용 및 컨텍스트 초과 방지)
        MAX_FILE_LENGTH = 10000
        if len(file_content) > MAX_FILE_LENGTH:
            file_content = file_content[:MAX_FILE_LENGTH] + "\n...(내용이 너무 길어 생략됨)..."
            print(f"[Analyzer] 파일 내용이 너무 길어 {MAX_FILE_LENGTH}자로 단축되었습니다.")
            
        file_context_msg = f"\n\n=== [첨부 파일 내용 (중요)] ===\n{file_content}\n=============================\n"
        
        # 사용자 입력이 매우 짧으면 파일 내용이 주가 됨을 알림
        if len(user_input.strip()) < 10:
             print("[Analyzer] 사용자 입력이 짧아 첨부 파일 내용을 중심으로 분석합니다.")

    # 2. 컨텍스트 구성
    review_data = state.get("review")
    current_analysis = state.get("analysis") # [NEW] 현재 분석 상태 (컨펌용)

    if current_analysis:
        # 이미 분석된 내용이 있다면 포맷팅 (JSON String)
        import json
        current_analysis_str = json.dumps(current_analysis, ensure_ascii=False, indent=2)
    else:
        current_analysis_str = "없음"

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
    if file_context_msg:
        # 파일 내용을 컨텍스트 최상단에 배치
        context_parts.append(file_context_msg)
        
    if web_context:
        context_parts.append(f"[웹에서 가져온 정보]\n{web_context}")
    if rag_context:
        context_parts.append(f"[기획서 작성 가이드]\n{rag_context}")
    context = "\n\n".join(context_parts) if context_parts else "없음"
    
    # 3. 프롬프트 구성 (시간 컨텍스트 주입)
    system_msg_content = get_time_context() + ANALYZER_SYSTEM_PROMPT

    # [FIX] 프롬프트 템플릿의 {review_data}, {current_analysis} 인자 전달
    user_msg_content = ANALYZER_USER_PROMPT.format(
        user_input=user_input,
        previous_plan=previous_plan if previous_plan else "없음",
        context=context,
        review_data=review_context,
        current_analysis=current_analysis_str
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

        # [Rule Override] 입력 길이가 충분히 길면(20자 이상), LLM이 확인 요청을 하더라도 강제로 진행
        # LLM이 안전 성향(Safety Bias)으로 인해 불필요한 확인을 시도하는 경우를 방지
        is_general = analysis_dict.get("is_general_query", False)
        need_info = analysis_dict.get("need_more_info", False)
        
        if need_info and not is_general:
            # 공백 제외 길이 체크
            input_len = len(user_input.strip())
            if input_len >= 20: 
                print(f"[Override] Input length({input_len}) >= 20. Forcing need_more_info=False (Fast Track).")
                analysis_dict["need_more_info"] = False
                analysis_dict["option_question"] = None
                analysis_dict["options"] = []

        # [Rule Override 2] (Safety Net)
        # 옵션 리스트가 비어있지 않다면, 이는 LLM이 추가 질문을 의도한 것이므로 무조건 need_more_info=True여야 함.
        # 또한, 옵션을 준다는 것은 '기획 제안'이므로 일반 잡담(is_general_query)일 수 없음.
        opts = analysis_dict.get("options", [])
        print(f"[DEBUG] Analyzer - options count: {len(opts)}, options: {opts[:2] if opts else 'EMPTY'}")
        
        if opts and len(opts) > 0:
             print(f"[DEBUG] Rule Override 2 적용됨! need_more_info=True, is_general=False 설정")
             analysis_dict["need_more_info"] = True
             analysis_dict["is_general_query"] = False

        print(f"[DEBUG] Analyzer Final - need_more_info: {analysis_dict.get('need_more_info')}, is_general: {analysis_dict.get('is_general_query')}")

        updates = {
            "analysis": analysis_dict,
            "need_more_info": analysis_dict.get("need_more_info", False),
            "options": analysis_dict.get("options", []),
            "option_question": analysis_dict.get("option_question"),
            "current_step": "analyze",
            # [CRITICAL] 새로운 분석 시작 시 이전 결과물(Stale State) 초기화
            "final_output": None,
            "generated_plan": None
        }
            
        return update_state(state, **updates)
        
    except Exception as e:
        print(f"[ERROR] Analyzer Failed: {e}")
        return update_state(state, error=str(e))
