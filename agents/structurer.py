"""
PlanCraft Agent - Structurer Agent (구조 설계자)

분석된 기획 의도를 바탕으로 전체 문서의 뼈대(목차 구조)를 설계하는 에이전트입니다.
단순한 나열이 아닌, 논리적 흐름(수미상관)을 고려하여 섹션을 배치합니다.

[Key Capabilities]
1. 프리셋 기반 확장:
   - 사용자가 선택한 모드(Fast/Balanced/Quality)에 맞춰 섹션의 깊이(Depth)와 넓이(Breadth)를 조절합니다.
   - Quality 모드 시 13개 이상의 심층 섹션을 의무적으로 생성합니다.
2. 자기 교정 (Self-Correction):
   - 생성된 목차가 기준 미달(섹션 수 부족 등)일 경우, 스스로 피드백을 생성하여 재설계합니다(Retry).
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
    
    # 1. 프리셋 및 입력 데이터 준비
    from utils.settings import get_preset
    generation_preset = state.get("generation_preset", "balanced")
    preset = get_preset(generation_preset)

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
        
    # 동적 LLM 생성 (프리셋 모델 적용)
    dynamic_llm = get_llm(
        model_type=preset.model_type, 
        temperature=target_temp
    ).with_structured_output(StructureResult)

    # 2. 프롬프트 구성 (시간 컨텍스트 주입)
    # min_sections를 프롬프트에 동적 전달
    user_msg_content = STRUCTURER_USER_PROMPT.format(
            analysis=analysis_str,
            context=context if context else "없음",
            min_sections=preset.min_sections,
            min_key_features=preset.min_key_features  # [NEW] 핵심 기능 수 전달
    )
    
    if feedback_msg:
        user_msg_content += feedback_msg

    messages = [
        {"role": "system", "content": get_time_context() + STRUCTURER_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg_content}
    ]
    
    # 3. LLM 호출 + Self-Reflection (최소 섹션 검증)
    # [UPDATE] 프리셋 기반 동적 설정 적용
    MIN_SECTIONS = preset.min_sections  # fast:7, balanced:9, quality:10
    MAX_RETRIES = preset.structurer_max_retries  # 모든 모드 2회 고정

    try:
        last_structure_dict = None

        for attempt in range(MAX_RETRIES):
            logger.info(f"[Structurer] 구조 설계 시도 ({attempt + 1}/{MAX_RETRIES})...")

            structure_result = dynamic_llm.invoke(messages)
            structure_dict = ensure_dict(structure_result)
            last_structure_dict = structure_dict

            section_count = len(structure_dict.get("sections", []))

            # [Self-Reflection] 최소 섹션 수 검증
            if section_count >= MIN_SECTIONS:
                logger.info(f"[Structurer] ✅ 구조화 완료: {section_count}개 섹션")
                return update_state(
                    state,
                    structure=structure_dict,
                    current_step="structure"
                )

            # 섹션 부족 시 재시도
            logger.warning(f"[Structurer] ⚠️ 섹션 부족 ({section_count}/{MIN_SECTIONS}개). 재설계합니다.")
            feedback = f"""
[System Critical Alert]:
- 생성된 섹션: {section_count}개 (최소 {MIN_SECTIONS}개 필요)
- 필수 섹션: 1.개요, 2.문제정의, 3.타겟/시장, 4.핵심기능, 5.비즈니스모델, 6.기술스택, 7.일정, 8.리스크, 9.KPI
- 모든 필수 섹션을 포함하여 다시 설계하세요!
"""
            messages.append({"role": "user", "content": feedback})

        # 재시도 후에도 부족하면 경고 후 사용
        logger.warning(f"[Structurer] ⚠️ 최소 섹션 미달이지만 결과 사용 ({len(last_structure_dict.get('sections', []))}개)")
        return update_state(
            state,
            structure=last_structure_dict,
            current_step="structure"
        )
        
    except Exception as e:
        logger.error(f"[Structurer] Failed: {e}")
        # Fallback: 9개 표준 섹션 구조 반환
        fallback_structure = {
            "title": "기획서 (자동 생성됨 - Fallback)",
            "sections": [
                {"name": "1. 서비스 개요", "content_guide": "서비스의 정의, 핵심 가치, 개발 배경을 작성하세요."},
                {"name": "2. 문제 정의 및 해결책", "content_guide": "해결하고자 하는 문제와 솔루션을 기술하세요."},
                {"name": "3. 타겟 사용자 및 시장 분석", "content_guide": "주요 타겟 사용자와 시장 규모를 분석하세요."},
                {"name": "4. 핵심 기능", "content_guide": "핵심 기능 3가지 이상을 상세히 기술하세요."},
                {"name": "5. 비즈니스 모델", "content_guide": "수익 창출 방안을 구체적으로 제시하세요."},
                {"name": "6. 기술 스택 및 아키텍처", "content_guide": "사용할 기술 스택과 시스템 구조를 설명하세요."},
                {"name": "7. 개발 일정 및 로드맵", "content_guide": "마일스톤별 개발 일정을 마크다운 테이블로 작성하세요."},
                {"name": "8. 리스크 분석 및 대응 방안", "content_guide": "예상 리스크와 대응 전략을 기술하세요."},
                {"name": "9. KPI 및 성공 지표", "content_guide": "정량적 목표와 측정 방법을 마크다운 테이블로 작성하세요."}
            ]
        }
        return update_state(
            state,
            structure=fallback_structure,
            error=f"구조화 실패(Fallback 적용): {str(e)}"
        )
