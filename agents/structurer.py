"""
PlanCraft Agent - Structurer Agent
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import StructureResult
from utils.time_context import get_time_context
from graph.state import PlanCraftState, update_state, ensure_dict
from prompts.structurer_prompt import STRUCTURER_SYSTEM_PROMPT, STRUCTURER_USER_PROMPT
from utils.file_logger import get_file_logger

# LLM 초기화 (run 함수 내에서 동적으로 생성함)
# structurer_llm = get_llm().with_structured_output(StructureResult)

def run(state: PlanCraftState) -> PlanCraftState:
    """
    구조화 에이전트 실행
    
    분석 결과(analysis)와 수집된 컨텍스트(context)를 바탕으로
    기획서의 전체 목차 구조(StructureResult)를 설계합니다.
    
    Args:
        state: user_input, analysis, rag_context, web_context를 포함한 상태
        
    Returns:
        Updated state with 'structure' field (dict)
        
    Example:
        >>> state = {"analysis": { "topic": "AI 앱", "features": [...] }, ...}
        >>> new_state = run(state)
        >>> print(new_state["structure"]["sections"])
        ['1. 개요', '2. 기능', ...]
    """
    logger = get_file_logger()
    
    # 1. 입력 데이터 준비 (Dict Access)
    user_input = state.get("user_input", "")
    analysis = state.get("analysis")
    
    if not analysis:
        logger.error("[Structurer] 분석 데이터 누락")
        return update_state(state, error="분석 데이터가 없습니다.")
        
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    context = f"{rag_context}\n{web_context}".strip()
    
    # Analysis 내용을 문자열로 변환
    analysis_str = str(analysis)
    
    # [Logic] LLM 초기화 (상황에 따른 Temperature 조절)
    # 기본은 정석적인(Conservative) 구조 설계를 위해 낮게 설정
    target_temp = 0.2
    
    previous_structure = state.get("structure")
    feedback_msg = ""

    # [Logic] 재설계(Refiner -> Restart) 모드 확인
    if previous_structure:
        # Refiner에서 품질 미달로 돌아온 경우: 다양성 확보를 위해 Temperature 상향
        target_temp = 0.6
        logger.info(f"[Structurer] 재설계 모드(Refiner Loop): Temperature를 {target_temp}로 상향")
        
        # Pydantic 객체일 경우 dict 변환
        prev_str = str(previous_structure)
        
        # 스스로 개선하도록 유도 (사용자 거절이 아님)
        feedback_msg = f"""
        =====================================================================
        [Self-Revision Mode]
        이전 설계({prev_str})가 최종 품질 기준을 충족하지 못해 다시 작성합니다.
        
        변경 지침:
        1. 이전 설계의 약점을 보완하고, 더 구체적이고 실현 가능한 구조로 개선하세요.
        2. 필요하다면 목차 구성을 과감하게 변경해도 좋습니다.
        =====================================================================
        """
        
    # 동적 LLM 생성
    dynamic_llm = get_llm(temperature=target_temp).with_structured_output(StructureResult)

    # 2. 프롬프트 구성 (시간 컨텍스트 주입)
    user_msg_content = STRUCTURER_USER_PROMPT.format(
            analysis=analysis_str,
            context=context if context else "없음"
    )
    
    if feedback_msg:
        user_msg_content += feedback_msg

    messages = [
        {"role": "system", "content": get_time_context() + STRUCTURER_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg_content}
    ]
    
    # 3. LLM 호출
    try:
        structure_result = dynamic_llm.invoke(messages)
        
        # 4. 상태 업데이트 (Pydantic -> Dict 일관성 보장)
        structure_dict = ensure_dict(structure_result)
            
        logger.info(f"[Structurer] 구조화 완료: {len(structure_dict.get('sections', []))}개 섹션")
            
        return update_state(
            state,
            structure=structure_dict,
            current_step="structure"
        )
        
    except Exception as e:
        logger.error(f"[Structurer] Failed: {e}")
        # Fallback: 기본 구조 반환
        fallback_structure = {
            "title": "기획서 (자동 생성됨 - Fallback)",
            "sections": [
                {"name": "1. 서비스 개요", "content_guide": "서비스의 정의, 핵심 가치, 개발 배경을 작성하세요."},
                {"name": "2. 주요 기능", "content_guide": "핵심 기능 3가지 이상을 상세히 기술하세요."},
                {"name": "3. 타겟 및 시장 분석", "content_guide": "주요 타겟 사용자와 시장 규모를 분석하세요."},
                {"name": "4. 비즈니스 모델", "content_guide": "수익 창출 방안을 구체적으로 제시하세요."},
                {"name": "5. 기대 효과", "content_guide": "서비스 도입 시 기대되는 정량적/정성적 효과를 기술하세요."}
            ]
        }
        return update_state(
            state, 
            structure=fallback_structure, 
            error=f"구조화 실패(Fallback 적용): {str(e)}"
        )
