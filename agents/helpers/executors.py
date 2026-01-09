"""
External Executors Helper
"""
from graph.state import PlanCraftState, update_state
from utils.settings import settings

def execute_web_search(user_input: str, rag_context: str, web_context: str, logger) -> str:
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


def execute_specialist_agents(state: PlanCraftState, user_input: str,
                                web_context: str, refine_count: int, logger) -> tuple:
    """
    [DEPRECATED] 전문 에이전트(Supervisor) 실행

    ⚠️ DEPRECATED: 이 함수는 더 이상 Writer에서 직접 호출되지 않습니다.
    워크플로우의 run_specialists 노드(graph/nodes/supervisor_node.py)에서
    Supervisor가 실행되며, Writer는 get_specialist_context()를 통해
    state에서 결과를 읽어옵니다.

    이 함수는 하위 호환성을 위해 유지되며, 호출 시 기존 분석 결과가
    있으면 재사용하여 중복 실행(Double Cost)을 방지합니다.

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

    # [FIX] 기존 분석 결과 확인 - 중복 실행 방지 (Double Cost Prevention)
    existing_analysis = state.get("specialist_analysis")

    if use_specialist_agents and refine_count == 0:
        # 1. 이미 분석 결과가 있으면 재사용 (워크플로우 노드에서 이미 실행됨)
        if existing_analysis:
            logger.info("[Writer] ✅ 워크플로우에서 미리 수행된 전문 분석 결과를 재사용합니다.")
            try:
                from agents.supervisor import NativeSupervisor
                supervisor = NativeSupervisor()
                specialist_context = supervisor._integrate_results(existing_analysis)
                return specialist_context, state
            except ImportError:
                # NativeSupervisor가 없으면 PlanSupervisor 시도 (호환성)
                from agents.supervisor import PlanSupervisor
                supervisor = PlanSupervisor()
                specialist_context = supervisor._integrate_results(existing_analysis)
                return specialist_context, state
            except Exception as e:
                logger.warning(f"[Writer] 분석 결과 통합 실패: {e}")
                return "", state

        # 2. 결과가 없을 때만 직접 실행 (Fallback - 워크플로우 노드 스킵된 경우)
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
                user_constraints=user_constraints,
                deep_analysis_mode=state.get("deep_analysis_mode", False) # [NEW]
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
