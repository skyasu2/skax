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
_writer_llm = None

def _get_writer_llm():
    """Writer LLM 지연 초기화"""
    global _writer_llm
    if _writer_llm is None:
        _writer_llm = get_llm(temperature=settings.LLM_TEMPERATURE_STRICT).with_structured_output(DraftResult)
    return _writer_llm


def _get_prompts_by_doc_type(state: PlanCraftState) -> tuple:
    """
    doc_type에 따라 적절한 프롬프트 반환
    - web_app_plan: IT/Tech 기획서 (기본값)
    - business_plan: 일반 사업 기획서
    """
    analysis = state.get("analysis")
    doc_type = "web_app_plan"  # 기본값
    
    if analysis:
        if isinstance(analysis, dict):
            doc_type = analysis.get("doc_type", "web_app_plan")
        else:
            doc_type = getattr(analysis, "doc_type", "web_app_plan")
    
    if doc_type == "business_plan":
        print(f"[Writer] 비IT 사업 기획서 모드로 작성합니다.")
        return BUSINESS_PLAN_SYSTEM_PROMPT, BUSINESS_PLAN_USER_PROMPT
    else:
        print(f"[Writer] IT/Tech 기획서 모드로 작성합니다.")
        return WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT


def run(state: PlanCraftState) -> PlanCraftState:
    """
    초안 작성 에이전트 실행
    """
    logger = get_file_logger()
    
    # 1. 입력 데이터 준비 (Dict Access)
    user_input = state.get("user_input", "")
    structure = state.get("structure")
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    web_urls = state.get("web_urls", [])
    
    if not structure:
        return update_state(state, error="구조화 데이터가 없습니다.")
    
    # Refinement Context
    previous_plan_context = ""
    refine_count = state.get("refine_count", 0)
    previous_plan = state.get("previous_plan")
    
    # 2. Review Context (Refine 모드일 때 필수)
    review_data = state.get("review")
    review_feedback_msg = ""
    
    if refine_count > 0 and review_data:
        # dict 또는 객체 처리
        if isinstance(review_data, dict):
            verdict = review_data.get("verdict", "")
            feedback_summary = review_data.get("feedback_summary", "")
            critical_issues = review_data.get("critical_issues", [])
            action_items = review_data.get("action_items", [])
        else:
            verdict = getattr(review_data, "verdict", "")
            feedback_summary = getattr(review_data, "feedback_summary", "")
            critical_issues = getattr(review_data, "critical_issues", [])
            action_items = getattr(review_data, "action_items", [])

        review_feedback_msg = f"""
=====================================================================
🚨 [REVISION REQUIRED] 이전 버전에 대한 심사 피드백 (반드시 반영할 것) 🚨
판정: {verdict}
지적 사항: {feedback_summary}
치명적 문제: {', '.join(critical_issues) if critical_issues else '없음'}
Action Items (실행 지침):
{chr(10).join([f'- {item}' for item in action_items])}
=====================================================================
"""
    
    if refine_count > 0 and previous_plan:
        previous_plan_context = f"\n<previous_version>\n{previous_plan}\n</previous_version>\n\n위 이전 버전과 심사 피드백을 참고하여 내용을 획기적으로 개선하세요.\n"

    # [NEW] doc_type에 따라 프롬프트 선택
    system_prompt, user_prompt_template = _get_prompts_by_doc_type(state)


    # =========================================================================
    # [NEW] 실시간 웹 검색 (수치 및 근거 보강)
    # =========================================================================
    try:
        from tools.web_search import should_search_web
        from tools.search_client import get_search_client
        
        # 1. 검색 여부 판단
        search_decision = should_search_web(user_input, rag_context)
        
        if search_decision.get("should_search") and search_decision.get("search_query"):
            query = search_decision["search_query"]
            logger.info(f"[Writer] 실시간 웹 검색 수행: '{query}'")
            
            # 2. 검색 수행 (Tavily)
            search_client = get_search_client()
            search_result = search_client.search(query)
            
            # 3. Context 보강
            if "[Web Search Failed]" not in search_result:
                if not web_context:
                    web_context = ""
                web_context += f"\n\n[Writer Search Result]\nKeyword: {query}\n{search_result}"
                logger.info("[Writer] 웹 데이터가 컨텍스트에 추가되었습니다.")
            else:
                 logger.warning(f"[Writer] 검색 실패 또는 스킵됨: {search_result}")

    except ImportError:
        logger.error("[Writer] 검색 모듈 로드 실패 (tools.web_search or tools.search_client)")
    except Exception as e:
        logger.error(f"[Writer] 웹 검색 중 오류 발생: {str(e)}")
    # =========================================================================

    # =========================================================================
    # [NEW] 전문 에이전트 분석 (Multi-Agent Supervisor)
    # =========================================================================
    # 
    # 4개의 전문 에이전트가 병렬로 분석을 수행합니다:
    # - MarketAgent: TAM/SAM/SOM 3단계, 경쟁사 실명 분석
    # - BMAgent: 수익 모델 다각화, 가격 전략
    # - FinancialAgent: 재무 시뮬레이션, BEP 계산
    # - RiskAgent: 8가지 리스크 카테고리
    #
    specialist_context = ""
    use_specialist_agents = state.get("use_specialist_agents", True)  # 기본 활성화
    
    if use_specialist_agents and refine_count == 0:  # 첫 작성 시에만 실행 (Refine 시 스킵)
        try:
            from agents.supervisor import PlanSupervisor
            
            logger.info("[Writer] 🤖 전문 에이전트 분석 시작 (Supervisor)...")
            
            # 분석 데이터 추출
            analysis_dict = state.get("analysis", {})
            if hasattr(analysis_dict, "model_dump"):
                analysis_dict = analysis_dict.model_dump()
            elif not isinstance(analysis_dict, dict):
                analysis_dict = {}
            
            target_market = analysis_dict.get("target_market", "일반 시장")
            target_users = analysis_dict.get("target_user", "일반 사용자")
            tech_stack = analysis_dict.get("tech_stack", "React Native + Node.js + PostgreSQL")
            user_constraints = analysis_dict.get("user_constraints", [])  # [NEW]
            
            # 웹 검색 결과를 리스트 형태로 변환
            web_search_list = []
            if web_context:
                # 간단한 파싱 (실제 검색 결과 형태에 맞게 조정)
                for line in web_context.split("\n"):
                    if line.strip():
                        web_search_list.append({"title": "", "content": line[:500]})
            
            # Supervisor 실행
            supervisor = PlanSupervisor()
            specialist_results = supervisor.run(
                service_overview=user_input,
                target_market=target_market,
                target_users=target_users,
                tech_stack=tech_stack,
                development_scope="MVP 3개월",
                web_search_results=web_search_list,
                user_constraints=user_constraints  # [NEW]
            )
            
            # 통합된 마크다운 컨텍스트 추출
            specialist_context = specialist_results.get("integrated_context", "")
            
            if specialist_context:
                logger.info("[Writer] ✓ 전문 에이전트 분석 완료!")
                logger.info(f"  - 시장 분석: {bool(specialist_results.get('market_analysis'))}")
                logger.info(f"  - BM 분석: {bool(specialist_results.get('business_model'))}")
                logger.info(f"  - 재무 계획: {bool(specialist_results.get('financial_plan'))}")
                logger.info(f"  - 리스크 분석: {bool(specialist_results.get('risk_analysis'))}")
            
            # 상태에 저장 (Refine 시 재사용)
            state = update_state(state, specialist_analysis=specialist_results)
            
        except ImportError as e:
            logger.warning(f"[Writer] Supervisor 모듈 로드 실패 (건너뜀): {e}")
        except Exception as e:
            logger.error(f"[Writer] 전문 에이전트 분석 중 오류 (건너뜀): {e}")
    
    elif refine_count > 0:
        # Refine 모드에서는 이전 분석 결과 재사용
        previous_specialist = state.get("specialist_analysis")
        if previous_specialist:
            from agents.supervisor import PlanSupervisor
            supervisor = PlanSupervisor()
            specialist_context = supervisor._integrate_results(previous_specialist)
            logger.info("[Writer] 이전 전문 에이전트 분석 결과 재사용")
    # =========================================================================




    # [NEW] 시각화 지침 생성 (프리셋 기반)
    from utils.settings import get_preset
    active_preset = state.get("generation_preset", settings.active_preset)
    preset = get_preset(active_preset)
    
    visual_instruction = ""
    if preset.include_diagrams > 0 or preset.include_charts > 0:
        visual_instruction = "\n\n📊 **시각적 요소 필수 요구사항 (Visual Elements Required)**:\n"
        if preset.include_diagrams > 0:
            # [FIX] 코드블록 문법을 명시적으로 지시
            visual_instruction += f"""- **Mermaid 다이어그램**: {preset.include_diagrams}개 이상 포함
  ⚠️ 반드시 아래 형식으로 작성 (코드블록 필수!):
  ```mermaid
  graph LR
      A[단계1] --> B[단계2]
  ```
  (사용자 여정 또는 시스템 아키텍처 시각화)
"""
        if preset.include_charts > 0:
            # [FIX] ASCII 차트 형식 명시
            visual_instruction += f"""- **ASCII 막대 그래프**: {preset.include_charts}개 이상 포함
  ⚠️ 반드시 테이블 내에서 아래 형식 사용:
  | 월 | MAU | 그래프 |
  |---|---:|---|
  | 1개월 | 1,000 | ▓░░░░░░░░░ 10% |
  | 6개월 | 5,000 | ▓▓▓▓▓░░░░░ 50% |
"""
        visual_instruction += "\n🚨 위 시각적 요소가 없으면 검증 실패로 재작성됩니다!\n"
        logger.info(f"[Writer] 시각적 요소 요청: 다이어그램 {preset.include_diagrams}개, 그래프 {preset.include_charts}개")

    # 2. 프롬프트 구성 (시간 컨텍스트 주입)
    structure_str = str(structure)
    
    # Web URLs 포맷팅
    web_urls_str = "없음"
    if web_urls:
        web_urls_str = "\n".join([f"- {url}" for url in web_urls])
    
    # [NEW] User Constraints Formatting
    user_constraints_str = "없음"
    # analysis는 위 Supervisor 섹션에서 이미 로드되었을 수 있으나, 안전하게 다시 확인
    analysis_obj = state.get("analysis")
    if analysis_obj:
        if isinstance(analysis_obj, dict):
            u_constraints = analysis_obj.get("user_constraints", [])
        else:
            u_constraints = getattr(analysis_obj, "user_constraints", [])
            
        if u_constraints:
            user_constraints_str = "\n".join([f"- {c}" for c in u_constraints])
        
    try:
        formatted_prompt = user_prompt_template.format(
            user_input=user_input,
            structure=structure_str,
            web_context=web_context if web_context else "없음",
            web_urls=web_urls_str,
            context=rag_context if rag_context else "없음",
            visual_instruction=visual_instruction,  # [NEW] 시각화 지침 주입
            user_constraints=user_constraints_str   # [NEW] 사용자 제약사항 주입
        )
    except KeyError as e:
        logger.error(f"[ERROR] Prompt Formatting Failed: {e}")
        return update_state(state, error=f"프롬프트 포맷 오류: {str(e)}")

    # =========================================================================
    # [NEW] 전문 에이전트 분석 결과 주입
    # =========================================================================
    if specialist_context:
        specialist_prompt = f"""

=====================================================================
🤖 전문 에이전트 분석 결과 (자동 생성됨 - 반드시 활용할 것!)
=====================================================================
⚠️ 아래 내용은 4개의 전문 AI 에이전트가 분석한 결과입니다.
⚠️ 시장 규모, 경쟁사, 재무 계획, 리스크는 이 내용을 기반으로 작성하세요!
⚠️ TAM/SAM/SOM, BEP, 리스크 테이블은 아래 데이터를 그대로 활용하세요!
=====================================================================

{specialist_context}

=====================================================================
"""
        formatted_prompt = specialist_prompt + formatted_prompt
        logger.info("[Writer] 전문 에이전트 분석 결과가 프롬프트에 주입되었습니다.")
    # =========================================================================


    # [NEW] Refinement Strategy (Writer에게 전달된 전략적 수정 지침)
    refinement_guideline = state.get("refinement_guideline")
    strategy_msg = ""

    if refine_count > 0 and refinement_guideline:
        if isinstance(refinement_guideline, dict):
            direction = refinement_guideline.get("overall_direction", "")
            guidelines = refinement_guideline.get("specific_guidelines", [])
        else:
            direction = getattr(refinement_guideline, "overall_direction", "")
            guidelines = getattr(refinement_guideline, "specific_guidelines", [])

        strategy_msg = f"""
=====================================================================
🚀 [STRATEGIC REVISION GUIDE] (전략적 수정 지침)
방향성: {direction}
상세 지침:
{chr(10).join([f'- {txt}' for txt in guidelines])}
=====================================================================
"""

    # 이전 버전 컨텍스트 및 피드백 추가 (최우선 순위)
    prepend_msg = ""
    if strategy_msg:
        prepend_msg += strategy_msg + "\n"
    if review_feedback_msg:
        prepend_msg += review_feedback_msg + "\n"
    if previous_plan_context:
         prepend_msg += previous_plan_context + "\n"
         
    formatted_prompt = prepend_msg + formatted_prompt

    # 시간 지시 추가 (일정/로드맵 정확성)
    formatted_prompt += get_time_instruction()

    # =========================================================================
    # [NEW] 프리셋 기반 시각적 요소 지침 추가
    # =========================================================================
    messages = [
        {"role": "system", "content": get_time_context() + system_prompt},
        {"role": "user", "content": formatted_prompt}
    ]

    
    
    # =========================================================================
    # 3. LLM 호출 및 Self-Correction (Reflection Loop)
    # =========================================================================
    #
    # Self-Reflection 패턴 (AlphaCodium 영감):
    # - 각 생성 결과를 자체 검증하여 품질 미달 시 재시도
    # - 프리셋에 따라 재시도 횟수 동적 조정
    #
    # ┌─────────────────────────────────────────────────────────────────────────┐
    # │                     Self-Reflection 검증 항목                           │
    # ├──────────────────────────┬──────────────────────────────────────────────┤
    # │ 검증 항목                │ 기준                                         │
    # ├──────────────────────────┼──────────────────────────────────────────────┤
    # │ 섹션 개수                │ >= WRITER_MIN_SECTIONS (기본 9개)            │
    # │ 섹션별 최소 길이         │ >= 100자 (너무 짧으면 부실)                  │
    # │ 마크다운 테이블 포함     │ 일정/KPI 섹션에 테이블 권장                  │
    # └──────────────────────────┴──────────────────────────────────────────────┘
    #
    # =========================================================================

    # 프리셋에서 재시도 횟수 가져오기 (동적)
    from utils.settings import get_preset
    active_preset = state.get("generation_preset", settings.active_preset)
    preset = get_preset(active_preset)
    max_retries = preset.writer_max_retries

    current_try = 0
    final_draft_dict = None
    last_draft_dict = None  # 마지막으로 생성된 결과 (부분이라도 보존)
    last_error = None
    validation_issues = []  # 검증 실패 이유 추적

    while current_try < max_retries:
        try:
            logger.info(f"[Writer] 초안 작성 시도 ({current_try + 1}/{max_retries})...")
            draft_result = _get_writer_llm().invoke(messages)
            
            # Pydantic -> Dict 일관성 보장
            draft_dict = ensure_dict(draft_result)

            # 마지막 결과 보존 (부분이라도)
            last_draft_dict = draft_dict

            # -----------------------------------------------------------------
            # [Reflection] Self-Check: 다중 품질 검증
            # -----------------------------------------------------------------
            sections = draft_dict.get("sections", [])
            section_count = len(sections)
            validation_issues = []
            missing_specialist = []  # Specialist 검증용 (초기화)

            # [UPDATE] 프리셋 기반 최소 섹션 수 (fast:7, balanced:9, quality:10)
            MIN_SECTIONS = preset.min_sections
            MIN_CONTENT_LENGTH = 100  # 섹션당 최소 글자수

            # 검증 1: 섹션 개수
            if section_count < MIN_SECTIONS:
                validation_issues.append(f"섹션 개수 부족 ({section_count}/{MIN_SECTIONS}개)")

            # 검증 2: 섹션별 최소 길이 (부실 섹션 검출)
            short_sections = []
            for sec in sections:
                sec_name = sec.get("name", "") if isinstance(sec, dict) else getattr(sec, "name", "")
                sec_content = sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", "")
                if len(sec_content) < MIN_CONTENT_LENGTH:
                    short_sections.append(sec_name)

            if short_sections and len(short_sections) >= 3:
                validation_issues.append(f"부실 섹션 다수 ({', '.join(short_sections[:3])}...)")

            # 검증 3: 마크다운 테이블 권장 (일정/로드맵 섹션)
            has_table = False
            for sec in sections:
                sec_content = sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", "")
                if "|" in sec_content and "---" in sec_content:
                    has_table = True
                    break

            # 테이블 없으면 경고만 (재시도는 안함)
            if not has_table:
                logger.info("[Writer Reflection] ℹ️ 마크다운 테이블 없음 (권장 사항)")

            # [FIX] 검증 4: 시각적 요소 (다이어그램) - 프리셋에서 요구 시 필수
            if preset.include_diagrams > 0:
                has_mermaid = any(
                    "```mermaid" in (sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", ""))
                    for sec in sections
                )
                if not has_mermaid:
                    validation_issues.append(f"Mermaid 다이어그램 누락 (필수 {preset.include_diagrams}개)")

            # [FIX] 검증 5: 시각적 요소 (차트/그래프) - 프리셋에서 요구 시 필수
            if preset.include_charts > 0:
                chart_indicators = ["▓", "░", "█", "■", "□", "●", "○"]
                has_chart = any(
                    any(ind in (sec.get("content", "") if isinstance(sec, dict) else getattr(sec, "content", "")) for ind in chart_indicators)
                    for sec in sections
                )
                if not has_chart:
                    validation_issues.append(f"ASCII 차트 누락 (필수 {preset.include_charts}개)")

            # [NEW] 검증 6: Specialist 분석 결과 반영 여부 (핵심 데이터 포함 체크)
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
                missing_specialist = [k for k, v in specialist_checks.items() if not v]
                if missing_specialist:
                    logger.warning(f"[Writer Reflection] ⚠️ Specialist 분석 미반영: {missing_specialist}")
                    # [FIX] 누락된 핵심 데이터를 validation_issues에 추가하여 재생성 유도
                    validation_issues.append(f"Specialist 핵심 데이터 누락: {', '.join(missing_specialist)}")

            # 검증 실패 시 재시도
            if validation_issues:
                logger.warning(f"[Writer Reflection] ⚠️ 검증 실패: {', '.join(validation_issues)}. 재작성합니다.")

                # [FIX] 피드백 메시지 강화 - 구체적 예시 포함
                visual_feedback = ""
                if preset.include_diagrams > 0:
                    visual_feedback += """
- 🚨 Mermaid 다이어그램 필수! 아래 형식을 복사해서 사용:
```mermaid
graph LR
    A[인지/유입] --> B[탐색/가입]
    B --> C[핵심 기능 사용]
    C --> D[전환/결제]
```
  (반드시 ```mermaid로 시작하고 ```로 끝나야 함!)"""
                if preset.include_charts > 0:
                    visual_feedback += """
- 🚨 ASCII 막대 그래프 필수! 아래 형식을 복사해서 사용:
| 월 | MAU | 그래프 |
|---|---:|---|
| 1개월 | 1,000 | ▓░░░░░░░░░ 10% |
| 6개월 | 5,000 | ▓▓▓▓▓░░░░░ 50% |"""

                # [NEW] Specialist 데이터 누락 시 구체적 피드백 추가
                specialist_feedback = ""
                if missing_specialist:
                    specialist_feedback = f"""
- ⚠️ Specialist 분석 핵심 데이터 누락: {', '.join(missing_specialist)}
- TAM/SAM/SOM 시장규모, 경쟁사 분석, BEP/손익분기점, 리스크 분석이 반드시 포함되어야 합니다!
- 위에서 제공된 '전문 에이전트 분석 결과' 내용을 그대로 활용하세요!"""

                feedback = f"""
[System Critical Alert]:
- 검증 실패 항목: {', '.join(validation_issues)}
- 현재 생성된 섹션: {section_count}개
- 최소 필수 섹션: {MIN_SECTIONS}개
- 필수 섹션 목록: 1.요약, 2.문제정의, 3.타겟/시장, 4.핵심기능, 5.비즈니스모델, 6.기술스택, 7.일정, 8.리스크, 9.KPI, 10.팀
- 각 섹션은 최소 {MIN_CONTENT_LENGTH}자 이상 작성하세요!
- 일정/KPI 섹션에는 마크다운 테이블을 포함하세요!{visual_feedback}{specialist_feedback}
"""
                messages.append({"role": "user", "content": feedback})
                current_try += 1
                last_error = f"검증 실패: {', '.join(validation_issues)}"
                continue

            # 통과 시 루프 탈출
            final_draft_dict = draft_dict
            logger.info(f"[Writer Reflection] ✅ Self-Check 통과 (섹션 {section_count}개, 테이블: {'있음' if has_table else '없음'}).")
            break

        except Exception as e:
            logger.error(f"[Writer Error] 생성 중 오류: {e}")
            current_try += 1
            last_error = str(e)
            
    # =========================================================================
    # 최종 결과 처리 (Fallback 전략)
    # =========================================================================
    #
    # 설계 원칙: "Workflow Deadlock 방지"
    # - MAX_RETRIES 초과 시에도 부분 결과가 있으면 워크플로우를 진행
    # - 무한 재시도 방지 및 사용자 경험 보장 (과제 환경에서 무한 대기 방지)
    # - Reviewer/Refiner 단계에서 추가 개선 기회 제공
    #
    if final_draft_dict:
        return update_state(
            state,
            draft=final_draft_dict,
            current_step="write"
        )
    elif last_draft_dict:
        # [Fallback] 재시도 실패 시 부분 결과로 진행 (Workflow Continuity 보장)
        logger.warning(f"[Writer] ⚠️ 최소 섹션 미달이지만 부분 결과 사용 ({len(last_draft_dict.get('sections', []))}개 섹션)")
        return update_state(
            state,
            draft=last_draft_dict,
            current_step="write"
        )
    else:
        # 완전 실패: 복구 불가능한 경우에만 에러 반환
        error_msg = f"Writer 작성 실패 (최대 재시도 초과): {last_error}"
        return update_state(state, error=error_msg)

