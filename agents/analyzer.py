"""
PlanCraft Agent - Analyzer Agent (분석가)

사용자의 초기 입력을 분석하여 기획의 방향성(Topic, Purpose)을 설정하고,
필수적인 핵심 기능(Key Features)과 제약사항(Constraints)을 도출하는 에이전트입니다.

[Key Capabilities]
1. 모드별 기능 제어:
   - GenerationPreset에 따라 최소 핵심 기능 개수(min_key_features)를 동적으로 조정합니다.
   - Fast(3개) / Balanced(5개) / Quality(7개)
2. HITL (Human-in-the-Loop) 상호작용:
   - 입력이 빈약할 경우(Situation B) 사용자의 승인을 얻기 위한 제안 모드로 작동합니다.
   - 입력이 구체적일 경우(Situation C) 바로 구조화 단계로 넘어가는 Fast Track을 지원합니다.
"""
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import AnalysisResult
from utils.time_context import get_time_context, get_time_instruction
from graph.state import PlanCraftState, update_state, ensure_dict
from prompts.analyzer_prompt import ANALYZER_SYSTEM_PROMPT, ANALYZER_USER_PROMPT
from utils.file_logger import get_file_logger

# LLM은 함수 내에서 동적 초기화 (설정 유연성)


def _set_hitl_options(analysis_dict: dict, user_input: str, clarification_questions: list) -> None:
    """
    HITL 옵션 설정 헬퍼 함수

    사용자에게 진행 여부를 확인하는 옵션을 설정합니다.
    """
    topic = analysis_dict.get("topic", user_input)
    questions_text = "\n".join(f"• {q}" for q in clarification_questions) if clarification_questions else ""

    if questions_text:
        analysis_dict["option_question"] = f"💡 '{topic}' 기획을 위해 확인이 필요합니다.\n{questions_text}"
    else:
        analysis_dict["option_question"] = f"💡 '{topic}' 기획을 이렇게 진행할까요?"

    analysis_dict["options"] = [
        {"id": "yes", "title": "네, 진행합니다", "description": "AI가 합리적인 가정으로 기획서 생성"},
        {"id": "retry", "title": "수정할게요", "description": "추가 정보 입력 후 진행"}
    ]


def _get_analyzer_llm(temperature: float = None):
    """
    Analyzer LLM 생성 (동적 설정)
    
    Args:
        temperature: 생성 온도 (None이면 기본값 0.7)
    """
    # 전역 캐싱 제거 -> 프리셋 변경에 즉시 대응
    # with_structured_output은 호출 시마다 파이프라인을 생성하므로
    # 너무 빈번한 호출이 부담된다면 settings 객체 내에 LRU 캐싱을 고려할 수 있음.
    # 하지만 현재 트래픽 수준에서는 매번 생성해도 무방함.
    
    # settings.LLM_TEMPERATURE_CREATIVE 기본값 활용
    from utils.settings import settings
    temp = temperature if temperature is not None else settings.LLM_TEMPERATURE_CREATIVE
    
    return get_llm(temperature=temp).with_structured_output(AnalysisResult)

def run(state: PlanCraftState) -> PlanCraftState:
    """
    요청 분석 에이전트 실행

    사용자 입력을 분석하여 기획의 주제, 목적, 주요 기능 등을 구조화된 데이터(AnalysisResult)로 변환합니다.

    Args:
        state: user_input, file_content 등을 포함한 상태

    Returns:
        Updated state with 'analysis' field

    Example:
        >>> state = {"user_input": "AI 헬스케어 앱 기획해줘"}
        >>> result = run(state)
        >>> print(result["analysis"]["topic"])
        'AI 헬스케어 앱'
    """
    # 1. 입력 데이터 준비 (Dict Access)
    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    previous_plan = state.get("previous_plan")
    
    # [FILE] 파일 내용 통합 (길이 제한 적용)
    from utils.settings import settings
    MAX_FILE_LENGTH = settings.MAX_FILE_LENGTH
    
    file_content = state.get("file_content")
    file_context_msg = ""
    
    if file_content:
        # 길이 제한 (토큰 비용 및 컨텍스트 초과 방지)
        if len(file_content) > MAX_FILE_LENGTH:
            file_content = file_content[:MAX_FILE_LENGTH] + "\n...(내용이 너무 길어 생략됨)..."
            get_file_logger().info(f"[Analyzer] 파일 내용이 너무 길어 {MAX_FILE_LENGTH}자로 단축되었습니다.")
            
        file_context_msg = f"\n\n=== [첨부 파일 내용 (중요)] ===\n{file_content}\n=============================\n"
        
        # 사용자 입력이 매우 짧으면 파일 내용이 주가 됨을 알림
        if len(user_input.strip()) < 10:
            get_file_logger().info("[Analyzer] 사용자 입력이 짧아 첨부 파일 내용을 중심으로 분석합니다.")

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
    
    # [Logic] 프리셋 로딩 (프롬프트 구성 및 LLM 설정용)
    from utils.settings import get_preset, settings
    active_preset = state.get("generation_preset", settings.active_preset)
    preset_config = get_preset(active_preset)

    # 3. 프롬프트 구성 (시간 컨텍스트 주입 + 동적 설정 적용)
    # min_key_features를 프롬프트에 주입 (f-string 사용 시 JSON 중괄호 충돌 방지를 위해 replace 사용)
    system_msg_content = get_time_context() + ANALYZER_SYSTEM_PROMPT.replace(
        "{min_key_features}", str(preset_config.min_key_features)
    )

    # 프롬프트 템플릿의 {review_data}, {current_analysis} 인자 전달
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
        # LLM 생성 및 실행
        # Analyzer는 창의적인 작업이므로 preset temperature 사용 (default: creative)
        temperature = preset_config.temperature
        analyzer = _get_analyzer_llm(temperature=temperature)
        analysis_result = analyzer.invoke(messages)
        
        # 5. 상태 업데이트 (Pydantic -> Dict 일관성 보장)
        analysis_dict = ensure_dict(analysis_result)

        # [NOTE] 키워드 기반 is_general_query 오버라이드 로직은 Smart Router로 이전됨
        # Smart Router가 intent 분류를 담당하므로, Analyzer는 LLM 결과를 신뢰합니다.
        # Router가 planning으로 판단한 경우에만 Analyzer가 호출됩니다.

        # [DEBUG] 분석 결과 로깅
        intent = state.get("intent", "unknown")
        get_file_logger().info(
            f"[Analyzer] LLM 분석 완료: topic='{analysis_dict.get('topic')}', "
            f"is_general={analysis_dict.get('is_general_query')}, "
            f"need_info={analysis_dict.get('need_more_info')}, "
            f"router_intent={intent}"
        )

        # =============================================================================
        # 2-Tier Gate System: Source Gate → Ambiguity Gate
        # =============================================================================
        #
        # [Source Gate] (Primary Decision)
        # - 템플릿 실행 (is_template_execution=True) → AutoPlan 기본 (HITL 스킵)
        # - 직접 입력 (is_template_execution=False) → NeedInfo 기본 (HITL 필요)
        #
        # [Ambiguity Gate] (Exception Handling)
        # - 직접 입력 + 슬롯 완전(0-1개 누락) → AutoPlan (예외적 스킵)
        # - 템플릿 + 슬롯 2개+ 누락 → NeedInfo (예외적 HITL)
        # =============================================================================

        is_general = analysis_dict.get("is_general_query", False)
        missing_slots = analysis_dict.get("missing_slots", [])
        clarification_questions = analysis_dict.get("clarification_questions", [])
        is_template = state.get("is_template_execution", False)

        # [FALLBACK] LLM이 missing_slots를 제공하지 않은 경우 코드에서 자체 검사
        intent_slots = analysis_dict.get("intent_slots")
        if not missing_slots and not is_general:
            detected_missing = []

            if intent_slots and isinstance(intent_slots, dict):
                if not intent_slots.get("target"):
                    detected_missing.append("target")
                if not intent_slots.get("purpose"):
                    detected_missing.append("purpose")
                if not intent_slots.get("output_type"):
                    detected_missing.append("output_type")
            else:
                input_lower = user_input.lower().strip()
                output_keywords = ["앱", "웹", "사이트", "플랫폼", "서비스", "시스템", "어플"]
                has_output_type = any(kw in input_lower for kw in output_keywords)
                detected_missing.append("target")
                if not has_output_type:
                    detected_missing.append("output_type")

            if detected_missing:
                missing_slots = detected_missing
                analysis_dict["missing_slots"] = missing_slots
                get_file_logger().info(f"[Fallback] 코드에서 슬롯 검사: missing_slots={missing_slots}")

        # [GUARDRAIL] 잡담 오분류 보정
        SERVICE_KEYWORDS = ["리뷰", "추천", "앱", "플랫폼", "기획", "개발", "아이디어", "창업", "사이트", "웹", "시스템", "서비스", "분석"]
        input_lower = user_input.lower().strip()

        if is_general and any(kw in input_lower for kw in SERVICE_KEYWORDS):
            get_file_logger().info(f"[Guardrail] 잡담 오분류 감지됨. 기획 모드로 강제 전환.")
            is_general = False
            analysis_dict["is_general_query"] = False
            analysis_dict["topic"] = analysis_dict.get("topic") if analysis_dict.get("topic") != "잡담" else f"{user_input} 서비스"

            if not missing_slots:
                missing_slots = ["target", "output_type"]
                analysis_dict["missing_slots"] = missing_slots
                analysis_dict["clarification_questions"] = [
                    "어떤 사용자를 대상으로 하시나요?",
                    "앱, 웹, 서비스 중 어떤 형태로 만들까요?"
                ]

        # =============================================================================
        # 2-Tier Gate Logic
        # =============================================================================
        num_missing = len(missing_slots)

        if is_general:
            # 잡담은 HITL 불필요
            analysis_dict["need_more_info"] = False
            get_file_logger().info("[Gate] 잡담 → AutoPlan (HITL 불필요)")

        elif is_template:
            # [Source Gate] 템플릿 실행 → 기본적으로 AutoPlan
            if num_missing >= 2:
                # [Ambiguity Gate] 예외: 필수 슬롯 2개+ 누락 시 HITL
                get_file_logger().info(f"[Gate] 템플릿 + 슬롯 {num_missing}개 누락 → NeedInfo (예외)")
                analysis_dict["need_more_info"] = True
                _set_hitl_options(analysis_dict, user_input, clarification_questions)
            else:
                # 템플릿 + 슬롯 충분 → AutoPlan
                get_file_logger().info(f"[Gate] 템플릿 + 슬롯 충분 → AutoPlan")
                analysis_dict["need_more_info"] = False
                analysis_dict["option_question"] = None
                analysis_dict["options"] = []

        else:
            # [Source Gate] 직접 입력 → 기본적으로 NeedInfo (HITL 필요)
            if num_missing <= 1:
                # [Ambiguity Gate] 예외: 슬롯이 충분하면 AutoPlan 허용
                get_file_logger().info(f"[Gate] 직접입력 + 슬롯 충분(누락 {num_missing}개) → AutoPlan (예외)")
                analysis_dict["need_more_info"] = False
                analysis_dict["option_question"] = None
                analysis_dict["options"] = []
            else:
                # 직접 입력 + 슬롯 부족 → NeedInfo (기본 동작)
                get_file_logger().info(f"[Gate] 직접입력 + 슬롯 {num_missing}개 누락 → NeedInfo (기본)")
                analysis_dict["need_more_info"] = True
                _set_hitl_options(analysis_dict, user_input, clarification_questions)

        # LLM이 명시적으로 옵션을 제공한 경우 HITL 활성화
        opts = analysis_dict.get("options", [])
        if opts and len(opts) > 0:
            analysis_dict["need_more_info"] = True
            analysis_dict["is_general_query"] = False

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
        get_file_logger().error(f"[Analyzer] Failed: {e}")
        # Fallback: 기본 분석 결과 반환 (운영 안전성 확보)
        fallback_analysis = {
            "topic": "분석 실패 (시스템 에러)",
            "purpose": "에러 발생으로 인한 기본값 생성",
            "target_users": "알 수 없음",
            "needs": [],
            "key_features": ["기본 기능 (에러 복구 모드)"],
            "is_general_query": False,
            "need_more_info": False,
            "general_answer": None
        }
        return update_state(state, analysis=fallback_analysis, error=f"Analyzer Error: {str(e)}")
