"""
Fetch Web Context Node
"""
from graph.state import PlanCraftState, update_state
from graph.nodes.common import update_step_history
from tools.web_search_executor import execute_web_search
from utils.tracing import trace_node
from utils.error_handler import handle_node_error

@trace_node("context", tags=["web", "search", "tavily"])
@handle_node_error
def fetch_web_context(state: PlanCraftState) -> PlanCraftState:
    """
    조건부 웹 정보 수집 노드

    [UPDATE] v1.5.0 - 프리셋 기반 웹 검색 최적화
    - fast: 1개 쿼리, basic depth
    - balanced: 3개 쿼리, basic depth
    - quality: 5개 쿼리, advanced depth

    Side-Effect: 외부 웹 API 호출 (Tavily Search)
    - 실패 시 재시도 안전함 (조회 전용, 멱등성 보장)
    - 검색 결과 캐싱으로 중복 호출 방지

    LangSmith: run_name="📚 컨텍스트 수집", tags=["rag", "retrieval", "web", "search", "tavily"]
    """
    import time
    from utils.settings import get_preset

    start_time = time.time()

    # [NEW] 프리셋 설정 로드
    preset_key = state.get("generation_preset", "balanced")
    preset = get_preset(preset_key)

    # [NEW] 웹 검색 비활성화 체크
    if not preset.web_search_enabled:
        print(f"[FetchWeb] 웹 검색 비활성화 (preset={preset_key})")
        return update_step_history(
            update_state(state, web_context=None, web_urls=[], web_sources=[]),
            "fetch_web", "SKIPPED", "웹 검색 비활성화됨",
            start_time=start_time
        )

    user_input = state.get("user_input", "")
    rag_context = state.get("rag_context")
    
    # [NEW] Analyzer 분석 결과가 있으면 검색 쿼리 최적화
    analysis = state.get("analysis")
    search_input = user_input
    
    if analysis:
        # Pydantic 모델 또는 Dict 처리
        if hasattr(analysis, "model_dump"):
            analysis = analysis.model_dump()
            
        if isinstance(analysis, dict):
            topic = analysis.get("topic")
            if topic and topic != user_input:
                # 주제가 명확해졌으므로 더 정확한 쿼리 생성 가능
                # 예: "그거..." -> "생성형 AI 트렌드"
                search_input = f"{topic} 시장 동향 및 성공 사례"
                print(f"[FetchWeb] 쿼리 최적화: '{user_input}' -> '{search_input}'")

    # 1. 웹 검색 실행 (Executor 위임)
    # [NEW] 프리셋 기반 파라미터 전달
    print(f"[FetchWeb] Preset={preset_key}, max_queries={preset.web_search_max_queries}, depth={preset.web_search_depth}")
    result = execute_web_search(
        search_input,
        rag_context,
        max_queries=preset.web_search_max_queries,
        search_depth=preset.web_search_depth
    )

    # [DEBUG] 웹 검색 결과 상세 로그
    print(f"[FETCH_WEB DEBUG] urls={len(result.get('urls', []))}, sources={len(result.get('sources', []))}, context_len={len(result.get('context') or '')}, error={result.get('error')}")

    # 2. 상태 업데이트
    existing_context = state.get("web_context")
    existing_urls = state.get("web_urls") or []
    existing_sources = state.get("web_sources") or []

    new_context_str = result["context"]
    new_urls = result["urls"]
    new_sources = result["sources"]
    error = result["error"]

    final_context = existing_context
    if new_context_str:
        final_context = f"{final_context}\n\n{new_context_str}" if final_context else new_context_str

    final_urls = list(dict.fromkeys(existing_urls + new_urls))

    # web_sources 병합 (중복 URL 제거)
    final_sources = existing_sources.copy()
    for src in new_sources:
        if not any(s.get("url") == src.get("url") for s in final_sources):
            final_sources.append(src)

    if error:
        new_state = update_state(
            state,
            web_context=None,
            web_urls=[],
            error=f"웹 조회 오류: {error}"
        )
    else:
        new_state = update_state(
            state,
            web_context=final_context,
            web_urls=final_urls,
            web_sources=final_sources,
            current_step="fetch_web"
        )

    status = "FAILED" if new_state.get("error") else "SUCCESS"
    url_count = len(new_state.get("web_urls") or [])
    summary = f"웹 정보 수집: {url_count}개 URL 참조"
    
    return update_step_history(new_state, "fetch_web", status, summary, new_state.get("error"), start_time=start_time)
