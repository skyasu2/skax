"""
PlanCraft Agent - Writer Agent (작가)

실질적인 기획서 본문을 작성하는 핵심 에이전트입니다.
구조화된 목차를 바탕으로 각 섹션에 들어갈 내용을 채우며, 전문 에이전트들의 분석 결과를 종합합니다.

[Key Capabilities]
1. 적응형 작성 전략 (Adaptive Writing Strategy):
   - Fast: 속도를 위해 한 번에 전체를 작성하는 Single-shot 방식을 사용합니다.
   - Balanced/Quality: ReAct 패턴으로 데이터 부족 시 자율적으로 도구를 호출합니다.
2. ReAct 패턴 (Reasoning + Acting):
   - [Thought] 작성 중 데이터 부족 판단
   - [Action] Specialist/Web/RAG 도구 호출
   - [Observation] 결과 확인 후 작성 계속
3. 능동적 데이터 통합:
   - RAG(Vector DB) 및 실시간 웹 검색(Active Search) 결과를 본문에 자연스럽게 녹여냅니다.
   - Mermaid 다이어그램 및 시각 자료 코드를 생성하여 문서의 가독성을 높입니다.
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import DraftResult
from utils.time_context import get_time_context, get_time_instruction
from graph.state import PlanCraftState, update_state, ensure_dict
from utils.settings import settings
from utils.file_logger import get_file_logger

# 헬퍼 함수 임포트 (Refactored)
from agents.writer_helpers import (
    get_prompts_by_doc_type,
    execute_web_search,
    execute_specialist_agents,
    build_visual_instruction,
    build_visual_feedback,
    build_review_context,
    build_refinement_context,
    validate_draft
)


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

    # 3. 컨텍스트 구성 (헬퍼 함수 위임)
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")

    # 웹 검색 실행 (Writer 자체 검색 제거 - Workflow에서 이미 수행됨)
    # web_context = execute_web_search(user_input, rag_context, web_context, logger)
    if not web_context:
        web_context = ""

    # 전문 에이전트 분석
    specialist_context, state = execute_specialist_agents(
        state, user_input, web_context, refine_count, logger
    )

    # 4. 프롬프트 구성
    system_prompt, user_prompt_template = get_prompts_by_doc_type(state)
    visual_instruction = build_visual_instruction(preset, logger)

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
        
        # [NEW] Quality 모드 전용 추가 지침 (양적 풍성함 강화)
        if preset.name == "quality":
            quality_instruction = """
\n=====================================================================
👑 **[Quality Mode] 최고 품질 작성 지침**
1. **핵심 기능(Key Features)**: 반드시 **6개 이상**의 핵심 기능을 상세히 기술하세요.
2. **섹션 분량**: 각 섹션은 최소 500자 이상, 깊이 있는 내용을 담으세요.
3. **참고 자료**: 인용된 모든 출처를 마지막에 '참고 자료' 섹션으로 정리하세요.
=====================================================================\n
"""
            formatted_prompt += quality_instruction

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
    review_context = build_review_context(state, refine_count)
    refinement_context = build_refinement_context(refine_count, preset.min_sections)

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

    # 5. LLM 호출
    messages = [
        {"role": "system", "content": get_time_context() + system_prompt},
        {"role": "user", "content": formatted_prompt}
    ]

    # [NEW] ReAct 모드 판단 (Balanced/Quality에서 활성화)
    # 1. 프리셋 설정 확인 (enable_writer_react)
    # 2. state 오버라이드 확인 (UI에서 개별 비활성화 가능)
    use_react_mode = (
        preset.enable_writer_react and                 # 프리셋에서 활성화됨
        refine_count == 0 and                          # 첫 작성 시에만
        state.get("enable_writer_react", True)         # state에서 비활성화 가능
    )

    if use_react_mode:
        logger.info(f"[Writer] 🔄 ReAct 모드 활성화 (preset={active_preset})")
        return _run_with_react_loop(
            state, messages, preset, specialist_context, logger
        )

    # Standard Mode (Fast 또는 ReAct 비활성화 시)
    writer_llm = get_llm(
        model_type=preset.model_type,
        temperature=preset.temperature
    ).with_structured_output(DraftResult)

    max_retries = preset.writer_max_retries
    final_draft_dict = None
    last_draft_dict = None
    last_error = None

    # Quality 모드 + ReAct 비활성화 시: 분할 작성 (Chunk Writing)
    if active_preset == "quality" and structure and not use_react_mode:
        logger.info("[Writer] 👑 Quality Mode: Chunk Writing 시작 (섹션별 상세 작성)")
        try:
            final_draft_dict = _write_in_chunks(
                writer_llm, 
                messages, 
                structure, 
                logger
            )
            # Chunk Writing 결과는 이미 Quality가 확보되었다고 가정하고 loop break
            # 단, 기본적인 포맷 검증은 한 번 수행
            issues = validate_draft(final_draft_dict, preset, specialist_context, refine_count, logger)
            if issues:
                logger.warning(f"[Writer] Chunk Writing 검증 이슈(무시됨): {issues}")
            
            return update_state(state, draft=final_draft_dict, current_step="write")
        except Exception as e:
            logger.error(f"[Writer] Chunk Writing 실패: {e}, Fallback to Standard Mode")
            # 실패 시 아래 표준 모드로 진행 (Fallback)

    # [Standard Mode] 통으로 작성 (Fast/Balanced or Quality Fallback)
    for current_try in range(max_retries):
        try:
            logger.info(f"[Writer] 초안 작성 시도 ({current_try + 1}/{max_retries})...")
            draft_result = writer_llm.invoke(messages)
            draft_dict = ensure_dict(draft_result)
            last_draft_dict = draft_dict

            # Self-Reflection 검증 (헬퍼 함수 위임)
            validation_issues = validate_draft(
                draft_dict, preset, specialist_context, refine_count, logger
            )

            if validation_issues:
                logger.warning(f"[Writer] 검증 실패: {', '.join(validation_issues)}")

                # 시각적 요소 누락 시 구체적인 예시 피드백 추가
                visual_feedback = build_visual_feedback(validation_issues, preset)
                base_feedback = f"[검증 실패] {', '.join(validation_issues)}. 모든 섹션을 완전히 작성하세요."
                feedback = base_feedback + visual_feedback if visual_feedback else base_feedback

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


def _write_in_chunks(llm, base_messages, structure_obj, logger):
    """
    [Quality Mode 전용] 섹션을 나누어 작성한 후 병합합니다.
    
    Args:
        llm: Writer LLM
        base_messages: 기본 시스템/유저 메시지
        structure_obj: Structurer 출력 객체 (sections 리스트 포함)
        logger: 로거
        
    Returns:
        dict: 합쳐진 DraftResult 딕셔너리
    """
    import copy
    from graph.state import ensure_dict

    structure_dict = ensure_dict(structure_obj)
    sections = structure_dict.get("sections", [])
    if not sections:
        raise ValueError("구조에 섹션 정보가 없습니다.")

    full_draft = {
        "title": structure_dict.get("title", "Business Plan"),
        "sections": [],
        "key_features": []  # 나중에 첫 청크에서 가져옴
    }
    
    # 청크 사이즈: 3개 섹션씩
    chunk_size = 3
    total_sections = len(sections)
    
    # 사용자 프롬프트(base_messages[-1])에서 기본 지시사항 추출
    base_user_content = base_messages[-1]["content"] if base_messages else ""
    
    for i in range(0, total_sections, chunk_size):
        chunk_sections = sections[i : i + chunk_size]
        chunk_titles = [s.get("title", s) if isinstance(s, dict) else str(s) for s in chunk_sections]
        
        logger.info(f"[Writer Chunk] 섹션 {i+1}~{min(i+chunk_size, total_sections)} 작성 중: {chunk_titles}")
        
        chunk_instruction = f"""
\n=====================================================================
🧩 **[Section Writing Phase {i//chunk_size + 1}]**
전체 비즈니스 기획서 중 아래 섹션들만 집중적으로 작성하세요.
절대 다른 섹션을 건너뛰거나 합치지 마세요.

**작성 대상 섹션**:
{chr(10).join([f'- {t}' for t in chunk_titles])}

이전 섹션 내용과 문맥이 이어지도록 자연스럽게 작성하세요.
=====================================================================
"""
        # 메시지 복사 후 지시사항 추가
        current_messages = copy.deepcopy(base_messages)
        # 기존 유저 메시지에 청크 지시 추가
        current_messages[-1]["content"] = base_user_content + chunk_instruction
        
        # LLM 호출
        result = llm.invoke(current_messages)
        result_dict = ensure_dict(result)
        
        # 결과 병합
        generated_sections = result_dict.get("sections", [])
        
        # 첫 번째 청크에서 메타데이터(Key Features 등) 가져오기
        if i == 0:
            full_draft["title"] = result_dict.get("title", full_draft["title"])
            full_draft["key_features"] = result_dict.get("key_features", [])
            full_draft["executive_summary"] = result_dict.get("executive_summary", "")
            
        full_draft["sections"].extend(generated_sections)
        
        # (선택) 다음 청크를 위한 컨텍스트 업데이트 로직이 필요할 수 있으나, 
        # 현재는 독립적으로 작성하되 전체 구조를 LLM이 알고 있으므로 넘어감.
        
    logger.info(f"[Writer Chunk] 병합 완료: 총 {len(full_draft['sections'])}개 섹션")
    return full_draft


# =============================================================================
# ReAct Pattern Implementation
# =============================================================================

# ReAct 설정
REACT_MAX_TOOL_CALLS = 3  # 최대 도구 호출 횟수
REACT_MAX_ITERATIONS = 5  # 최대 루프 반복 횟수


def _run_with_react_loop(
    state: PlanCraftState,
    base_messages: list,
    preset,
    specialist_context: str,
    logger
) -> PlanCraftState:
    """
    ReAct 패턴으로 초안 작성 (Tool 호출 가능)

    Writer가 작성 중 데이터 부족을 자율적으로 판단하고,
    필요시 Specialist/Web/RAG 도구를 호출하여 데이터를 보강합니다.

    Flow:
        [Thought] "시장 데이터가 부족하다"
        [Action]  request_specialist_analysis("market", "TAM/SAM/SOM 분석")
        [Observation] {tam: "10조원", ...}
        [Continue] 작성 계속...
        [Final Answer] DraftResult JSON

    Args:
        state: 현재 워크플로우 상태
        base_messages: 시스템/유저 메시지
        preset: 프리셋 설정
        specialist_context: 기존 Specialist 분석 결과
        logger: 로거

    Returns:
        PlanCraftState: draft 필드가 추가된 상태
    """
    from langchain_core.messages import AIMessage, ToolMessage
    from tools.writer_tools import get_writer_tools
    from prompts.writer_prompt import WRITER_REACT_INSTRUCTION

    logger.info("[Writer ReAct] ReAct 루프 시작")

    # 1. 도구 준비
    tools = get_writer_tools()
    tool_map = {tool.name: tool for tool in tools}

    # 2. LLM with Tools 설정
    llm = get_llm(
        model_type=preset.model_type,
        temperature=preset.temperature
    )
    llm_with_tools = llm.bind_tools(tools)

    # 3. ReAct 지침을 시스템 프롬프트에 추가
    messages = base_messages.copy()
    messages[0]["content"] += "\n\n" + WRITER_REACT_INSTRUCTION

    # 4. ReAct 루프
    tool_call_count = 0
    iteration = 0
    tool_results_context = []  # 도구 호출 결과 누적

    while iteration < REACT_MAX_ITERATIONS:
        iteration += 1
        logger.info(f"[Writer ReAct] Iteration {iteration}/{REACT_MAX_ITERATIONS}")

        try:
            response = llm_with_tools.invoke(messages)

            # Tool 호출 감지
            if hasattr(response, 'tool_calls') and response.tool_calls:
                # AIMessage 추가
                messages.append(response)

                for tool_call in response.tool_calls:
                    if tool_call_count >= REACT_MAX_TOOL_CALLS:
                        logger.warning(f"[Writer ReAct] 최대 도구 호출 횟수 도달 ({REACT_MAX_TOOL_CALLS})")
                        # 더 이상 도구 호출하지 않고 종료
                        messages.append(ToolMessage(
                            content="[LIMIT] 도구 호출 횟수 제한에 도달했습니다. 현재까지의 정보로 작성을 완료하세요.",
                            tool_call_id=tool_call['id']
                        ))
                        break

                    tool_name = tool_call['name']
                    tool_args = tool_call['args']

                    logger.info(f"[Writer ReAct] Tool 호출: {tool_name}({list(tool_args.keys())})")

                    # Tool 실행
                    result = _execute_react_tool(tool_name, tool_args, tool_map, logger)
                    tool_call_count += 1

                    # 결과 저장
                    tool_results_context.append({
                        "tool": tool_name,
                        "query": tool_args.get("query", tool_args.get("specialist_type", "")),
                        "result_preview": result[:200] + "..." if len(result) > 200 else result
                    })

                    # ToolMessage 추가
                    messages.append(ToolMessage(
                        content=result,
                        tool_call_id=tool_call['id']
                    ))

                # 도구 호출 후 루프 계속
                continue

            else:
                # Tool 호출 없음 = 최종 응답 준비 완료
                logger.info("[Writer ReAct] Tool 호출 완료, 최종 작성 단계로 진입")
                break

        except Exception as e:
            logger.error(f"[Writer ReAct] 루프 오류: {e}")
            break

    # 5. 최종 Structured Output 생성
    logger.info("[Writer ReAct] 최종 DraftResult 생성 중...")

    # 도구 결과를 컨텍스트로 추가
    if tool_results_context:
        tools_summary = "\n\n".join([
            f"### {tr['tool']} 결과 ({tr['query']})\n{tr['result_preview']}"
            for tr in tool_results_context
        ])
        additional_context = f"""
=====================================================================
🔧 ReAct 도구 호출 결과 (반드시 활용할 것!)
=====================================================================
{tools_summary}
=====================================================================
"""
        # 유저 메시지에 추가
        messages[-1] = {"role": "user", "content": messages[1]["content"] + additional_context}

    # Structured Output LLM으로 최종 작성
    final_llm = get_llm(
        model_type=preset.model_type,
        temperature=preset.temperature
    ).with_structured_output(DraftResult)

    try:
        # 최종 메시지 정리 (Tool 관련 메시지 제거하고 컨텍스트만 유지)
        final_messages = [
            messages[0],  # System
            {"role": "user", "content": messages[1]["content"]}  # User (원본)
        ]

        # 도구 결과 컨텍스트 추가
        if tool_results_context:
            tools_context = "\n".join([
                f"- {tr['tool']}: {tr['result_preview']}"
                for tr in tool_results_context
            ])
            final_messages[1]["content"] += f"\n\n[추가 데이터 - ReAct 도구 결과]\n{tools_context}"

        final_result = final_llm.invoke(final_messages)
        draft_dict = ensure_dict(final_result)

        section_count = len(draft_dict.get("sections", []))
        logger.info(f"[Writer ReAct] ✅ 작성 완료 (섹션 {section_count}개, 도구 호출 {tool_call_count}회)")

        return update_state(state, draft=draft_dict, current_step="write")

    except Exception as e:
        logger.error(f"[Writer ReAct] 최종 작성 실패: {e}")
        return update_state(state, error=f"Writer ReAct 실패: {str(e)}")


def _execute_react_tool(
    tool_name: str,
    tool_args: dict,
    tool_map: dict,
    logger
) -> str:
    """
    ReAct 도구 실행 헬퍼

    Args:
        tool_name: 도구 이름
        tool_args: 도구 인자
        tool_map: 도구 이름 → 도구 객체 맵
        logger: 로거

    Returns:
        도구 실행 결과 문자열
    """
    if tool_name not in tool_map:
        return f"[ERROR] 알 수 없는 도구: {tool_name}. 사용 가능: {list(tool_map.keys())}"

    tool = tool_map[tool_name]

    try:
        result = tool.invoke(tool_args)
        logger.info(f"[Writer ReAct] Tool '{tool_name}' 성공: {len(result)}자")
        return result
    except Exception as e:
        logger.error(f"[Writer ReAct] Tool '{tool_name}' 실패: {e}")
        return f"[ERROR] {tool_name} 실행 실패: {str(e)}. 가정으로 진행하세요."

