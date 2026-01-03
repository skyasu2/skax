"""
PlanCraft Agent - Writer Agent
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import DraftResult
from utils.time_context import get_time_context, get_time_instruction
from graph.state import PlanCraftState, update_state, ensure_dict
from utils.settings import settings
from utils.file_logger import get_file_logger

# 프롬프트 임포트 (IT용 / 일반 사업용)
from prompts.writer_prompt import WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT
from prompts.business_plan_prompt import BUSINESS_PLAN_SYSTEM_PROMPT, BUSINESS_PLAN_USER_PROMPT

# LLM은 함수 내에서 지연 초기화 (환경 변수 로딩 타이밍 이슈 방지)
# LLM은 함수 내에서 동적으로 생성 (프리셋 적용)


def _get_prompts_by_doc_type(state: PlanCraftState) -> tuple:
    """
    doc_type에 따라 적절한 프롬프트 반환

    Args:
        state: 현재 워크플로우 상태

    Returns:
        Tuple[str, str]: (system_prompt, user_prompt_template)
    """
    logger = get_file_logger()
    analysis = state.get("analysis")
    analysis_dict = ensure_dict(analysis)
    doc_type = analysis_dict.get("doc_type", "web_app_plan")

    if doc_type == "business_plan":
        logger.info("[Writer] 비IT 사업 기획서 모드로 작성합니다.")
        return BUSINESS_PLAN_SYSTEM_PROMPT, BUSINESS_PLAN_USER_PROMPT
    else:
        logger.info("[Writer] IT/Tech 기획서 모드로 작성합니다.")
        return WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT


# =============================================================================
# Helper Functions (리팩토링 - 함수 분리)
# =============================================================================

def _build_review_context(state: PlanCraftState, refine_count: int) -> str:
    """
    Reviewer 피드백을 컨텍스트 문자열로 변환

    Args:
        state: 현재 상태
        refine_count: 개선 횟수

    Returns:
        str: 리뷰 피드백 메시지 (없으면 빈 문자열)
    """
    if refine_count == 0:
        return ""

    review_data = state.get("review")
    if not review_data:
        return ""

    review_dict = ensure_dict(review_data)
    verdict = review_dict.get("verdict", "")
    feedback_summary = review_dict.get("feedback_summary", "")
    critical_issues = review_dict.get("critical_issues", [])
    action_items = review_dict.get("action_items", [])

    return f"""
=====================================================================
🚨 [REVISION REQUIRED] 이전 버전에 대한 심사 피드백 (반드시 반영할 것) 🚨
판정: {verdict}
지적 사항: {feedback_summary}
치명적 문제: {', '.join(critical_issues) if critical_issues else '없음'}
Action Items (실행 지침):
{chr(10).join([f'- {item}' for item in action_items])}
=====================================================================
"""


def _build_refinement_context(refine_count: int, min_sections: int) -> str:
    """
    개선 모드용 컨텍스트 생성

    Args:
        refine_count: 현재 개선 횟수
        min_sections: 최소 섹션 수

    Returns:
        str: 개선 모드 지침 메시지
    """
    if refine_count == 0:
        return ""

    return f"""
=====================================================================
🔄 [REFINEMENT MODE] 개선 라운드 {refine_count} - 완전히 새로 작성하세요!
=====================================================================

⚠️ 이번은 {refine_count}번째 개선 시도입니다.
⚠️ 이전 버전의 피드백을 반영하여 **처음부터 완전히 새로 작성**하세요.
⚠️ 이전 버전을 참조하지 마세요. 아래 structure를 따라 **모든 {min_sections}개 섹션**을 작성하세요!

🎯 필수 요구사항:
1. sections 배열에 **정확히 {min_sections}개 이상**의 섹션 포함
2. 각 섹션은 **최소 300자 이상** 상세하게 작성
3. structure에 정의된 **모든 섹션**을 빠짐없이 작성
4. 부분 출력 절대 금지 - 완전한 기획서 출력 필수

=====================================================================
"""


def _execute_web_search(user_input: str, rag_context: str, web_context: str, logger) -> str:
    """
    실시간 웹 검색 수행

    Args:
        user_input: 사용자 입력
        rag_context: RAG 컨텍스트
        web_context: 기존 웹 컨텍스트
        logger: 로거 인스턴스

    Returns:
        str: 업데이트된 웹 컨텍스트
    """
    try:
        from tools.web_search import should_search_web
        from tools.search_client import get_search_client

        search_decision = should_search_web(user_input, rag_context)

        if search_decision.get("should_search") and search_decision.get("search_query"):
            query = search_decision["search_query"]
            logger.info(f"[Writer] 실시간 웹 검색 수행: '{query}'")

            search_client = get_search_client()
            search_result = search_client.search(query)

            if "[Web Search Failed]" not in search_result:
                if not web_context:
                    web_context = ""
                web_context += f"\n\n[Writer Search Result]\nKeyword: {query}\n{search_result}"
                logger.info("[Writer] 웹 데이터가 컨텍스트에 추가되었습니다.")
            else:
                logger.warning(f"[Writer] 검색 실패 또는 스킵됨: {search_result}")

    except ImportError:
        logger.error("[Writer] 검색 모듈 로드 실패")
    except Exception as e:
        logger.error(f"[Writer] 웹 검색 중 오류 발생: {str(e)}")

    return web_context


def _execute_specialist_agents(state: PlanCraftState, user_input: str,
                                web_context: str, refine_count: int, logger) -> tuple:
    """
    전문 에이전트(Supervisor) 실행

    Args:
        state: 현재 상태
        user_input: 사용자 입력
        web_context: 웹 컨텍스트
        refine_count: 개선 횟수
        logger: 로거 인스턴스

    Returns:
        Tuple[str, PlanCraftState]: (specialist_context, updated_state)
    """
    specialist_context = ""
    use_specialist_agents = state.get("use_specialist_agents", True)

    if use_specialist_agents and refine_count == 0:
        try:
            from agents.supervisor import PlanSupervisor

            logger.info("[Writer] 🤖 전문 에이전트 분석 시작 (Supervisor)...")

            analysis_dict = state.get("analysis", {})
            if hasattr(analysis_dict, "model_dump"):
                analysis_dict = analysis_dict.model_dump()
            elif not isinstance(analysis_dict, dict):
                analysis_dict = {}

            target_market = analysis_dict.get("target_market", "일반 시장")
            target_users = analysis_dict.get("target_user", "일반 사용자")
            tech_stack = analysis_dict.get("tech_stack", "React Native + Node.js + PostgreSQL")
            user_constraints = analysis_dict.get("user_constraints", [])

            web_search_list = []
            if web_context:
                for line in web_context.split("\n"):
                    if line.strip():
                        web_search_list.append({"title": "", "content": line[:500]})

            supervisor = PlanSupervisor()
            specialist_results = supervisor.run(
                service_overview=user_input,
                target_market=target_market,
                target_users=target_users,
                tech_stack=tech_stack,
                development_scope="MVP 3개월",
                web_search_results=web_search_list,
                user_constraints=user_constraints
            )

            specialist_context = specialist_results.get("integrated_context", "")

            if specialist_context:
                logger.info("[Writer] ✓ 전문 에이전트 분석 완료!")

            state = update_state(state, specialist_analysis=specialist_results)

        except ImportError as e:
            logger.warning(f"[Writer] Supervisor 모듈 로드 실패: {e}")
        except Exception as e:
            logger.error(f"[Writer] 전문 에이전트 분석 중 오류: {e}")

    elif refine_count > 0:
        previous_specialist = state.get("specialist_analysis")
        if previous_specialist:
            from agents.supervisor import PlanSupervisor
            supervisor = PlanSupervisor()
            specialist_context = supervisor._integrate_results(previous_specialist)
            logger.info("[Writer] 이전 전문 에이전트 분석 결과 재사용")

    return specialist_context, state


def _build_visual_instruction(preset, logger) -> str:
    """
    프리셋 기반 시각적 요소 지침 생성

    Args:
        preset: 생성 프리셋 설정
        logger: 로거 인스턴스

    Returns:
        str: 시각화 지침 문자열
    """
    if preset.include_diagrams == 0 and preset.include_charts == 0:
        return ""

    visual_instruction = "\n\n📊 **시각적 요소 필수 요구사항**:\n"

    if preset.include_diagrams > 0:
        visual_instruction += f"""- **Mermaid 다이어그램**: {preset.include_diagrams}개 이상
  ```mermaid
  graph TB
      A[단계1] --> B[단계2]
  ```
"""
    if preset.include_charts > 0:
        visual_instruction += f"""- **ASCII 막대 그래프**: {preset.include_charts}개 이상
  | 월 | MAU | 그래프 |
  |---|---:|---|
  | 1개월 | 1,000 | ▓░░░░░░░░░ 10% |
"""
    visual_instruction += "\n🚨 위 시각적 요소가 없으면 검증 실패!\n"
    logger.info(f"[Writer] 시각적 요소 요청: 다이어그램 {preset.include_diagrams}개, 차트 {preset.include_charts}개")

    return visual_instruction


def _validate_draft(draft_dict: dict, preset, specialist_context: str,
                    refine_count: int, logger) -> list:
    """
    생성된 초안 검증 (Self-Reflection)

    Args:
        draft_dict: 생성된 초안
        preset: 프리셋 설정
        specialist_context: 전문 에이전트 컨텍스트
        refine_count: 개선 횟수
        logger: 로거

    Returns:
        List[str]: 검증 실패 항목 목록 (빈 리스트면 통과)
    """
    sections = draft_dict.get("sections", [])
    section_count = len(sections)
    validation_issues = []

    MIN_SECTIONS = preset.min_sections
    MIN_CONTENT_LENGTH = 100

    # 검증 1: 섹션 개수
    if section_count < MIN_SECTIONS:
        validation_issues.append(f"섹션 개수 부족 ({section_count}/{MIN_SECTIONS}개)")

    # 검증 2: 섹션별 최소 길이
    short_sections = []
    for sec in sections:
        sec_name = sec.get("name", "") if isinstance(sec, dict) else getattr(sec, "name", "")
        sec_content = sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", "")
        if len(sec_content) < MIN_CONTENT_LENGTH:
            short_sections.append(sec_name)

    if short_sections and len(short_sections) >= 3:
        validation_issues.append(f"부실 섹션 다수 ({', '.join(short_sections[:3])}...)")

    # 검증 3: Mermaid 다이어그램
    if preset.include_diagrams > 0:
        has_mermaid = any(
            "```mermaid" in (sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", ""))
            for sec in sections
        )
        if not has_mermaid:
            validation_issues.append(f"Mermaid 다이어그램 누락")

    # 검증 4: ASCII 차트
    if preset.include_charts > 0:
        chart_indicators = ["▓", "░", "█", "■", "□", "●", "○"]
        has_chart = any(
            any(ind in (sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", "")) for ind in chart_indicators)
            for sec in sections
        )
        if not has_chart:
            validation_issues.append(f"ASCII 차트 누락")

    # 검증 5: Specialist 분석 반영
    if specialist_context and refine_count == 0:
        all_content = " ".join(
            sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", "")
            for sec in sections
        )
        specialist_checks = {
            "TAM/SAM/SOM": any(kw in all_content for kw in ["TAM", "SAM", "SOM", "시장 규모"]),
            "경쟁사 분석": any(kw in all_content for kw in ["경쟁사", "Competitor", "차별점"]),
            "BEP/손익분기": any(kw in all_content for kw in ["BEP", "손익분기", "손익 분기"]),
            "리스크": any(kw in all_content for kw in ["리스크", "Risk", "대응 방안", "위험"]),
        }
        missing = [k for k, v in specialist_checks.items() if not v]
        if missing:
            validation_issues.append(f"Specialist 데이터 누락: {', '.join(missing)}")

    return validation_issues


def run(state: PlanCraftState) -> PlanCraftState:
    """
    초안 작성 에이전트 실행

    Args:
        state: 현재 워크플로우 상태 (structure 필수)

    Returns:
        PlanCraftState: draft 필드가 추가된 상태
    """
    logger = get_file_logger()

    # 1. 입력 검증
    user_input = state.get("user_input", "")
    structure = state.get("structure")
    if not structure:
        return update_state(state, error="구조화 데이터가 없습니다.")

    # 2. 설정 로드
    from utils.settings import get_preset
    active_preset = state.get("generation_preset", settings.active_preset)
    preset = get_preset(active_preset)
    refine_count = state.get("refine_count", 0)

    # 3. 컨텍스트 구성 (헬퍼 함수 사용)
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")

    # 웹 검색 실행
    web_context = _execute_web_search(user_input, rag_context, web_context, logger)

    # 전문 에이전트 분석
    specialist_context, state = _execute_specialist_agents(
        state, user_input, web_context, refine_count, logger
    )

    # 4. 프롬프트 구성
    system_prompt, user_prompt_template = _get_prompts_by_doc_type(state)
    visual_instruction = _build_visual_instruction(preset, logger)

    # User Constraints 추출
    user_constraints_str = "없음"
    analysis_obj = state.get("analysis")
    if analysis_obj:
        u_constraints = analysis_obj.get("user_constraints", []) if isinstance(analysis_obj, dict) \
            else getattr(analysis_obj, "user_constraints", [])
        if u_constraints:
            user_constraints_str = "\n".join([f"- {c}" for c in u_constraints])

    # Web URLs 포맷팅
    web_urls = state.get("web_urls", [])
    web_urls_str = "\n".join([f"- {url}" for url in web_urls]) if web_urls else "없음"

    try:
        formatted_prompt = user_prompt_template.format(
            user_input=user_input,
            structure=str(structure),
            web_context=web_context if web_context else "없음",
            web_urls=web_urls_str,
            context=rag_context if rag_context else "없음",
            visual_instruction=visual_instruction,
            user_constraints=user_constraints_str
        )
    except KeyError as e:
        return update_state(state, error=f"프롬프트 포맷 오류: {str(e)}")

    # 전문 에이전트 결과 주입
    if specialist_context:
        specialist_header = f"""
=====================================================================
🤖 전문 에이전트 분석 결과 (반드시 활용할 것!)
=====================================================================
{specialist_context}
=====================================================================
"""
        formatted_prompt = specialist_header + formatted_prompt

    # Refinement 컨텍스트 추가
    review_context = _build_review_context(state, refine_count)
    refinement_context = _build_refinement_context(refine_count, preset.min_sections)

    # Refinement Strategy
    strategy_msg = ""
    refinement_guideline = state.get("refinement_guideline")
    if refine_count > 0 and refinement_guideline:
        direction = refinement_guideline.get("overall_direction", "") if isinstance(refinement_guideline, dict) \
            else getattr(refinement_guideline, "overall_direction", "")
        guidelines = refinement_guideline.get("specific_guidelines", []) if isinstance(refinement_guideline, dict) \
            else getattr(refinement_guideline, "specific_guidelines", [])
        strategy_msg = f"🚀 방향: {direction}\n지침: {chr(10).join([f'- {g}' for g in guidelines])}\n"

    prepend_msg = strategy_msg + review_context + refinement_context
    formatted_prompt = prepend_msg + formatted_prompt + get_time_instruction()

    # 5. LLM 호출 (Self-Reflection Loop)
    messages = [
        {"role": "system", "content": get_time_context() + system_prompt},
        {"role": "user", "content": formatted_prompt}
    ]

    writer_llm = get_llm(
        model_type=preset.model_type,
        temperature=preset.temperature
    ).with_structured_output(DraftResult)

    max_retries = preset.writer_max_retries
    final_draft_dict = None
    last_draft_dict = None
    last_error = None

    for current_try in range(max_retries):
        try:
            logger.info(f"[Writer] 초안 작성 시도 ({current_try + 1}/{max_retries})...")
            draft_result = writer_llm.invoke(messages)
            draft_dict = ensure_dict(draft_result)
            last_draft_dict = draft_dict

            # Self-Reflection 검증
            validation_issues = _validate_draft(
                draft_dict, preset, specialist_context, refine_count, logger
            )

            if validation_issues:
                logger.warning(f"[Writer] 검증 실패: {', '.join(validation_issues)}")
                feedback = f"[검증 실패] {', '.join(validation_issues)}. 모든 섹션을 완전히 작성하세요."
                messages.append({"role": "user", "content": feedback})
                last_error = f"검증 실패: {', '.join(validation_issues)}"
                continue

            # 통과
            final_draft_dict = draft_dict
            section_count = len(draft_dict.get("sections", []))
            logger.info(f"[Writer] ✅ Self-Check 통과 (섹션 {section_count}개)")
            break

        except Exception as e:
            logger.error(f"[Writer Error] {e}")
            last_error = str(e)

    # 6. 결과 반환
    if final_draft_dict:
        return update_state(state, draft=final_draft_dict, current_step="write")
    elif last_draft_dict:
        logger.warning("[Writer] ⚠️ 부분 결과 사용")
        return update_state(state, draft=last_draft_dict, current_step="write")
    else:
        return update_state(state, error=f"Writer 실패: {last_error}")

