"""
PlanCraft Agent - Web Search Executor

웹 검색 실행 로직을 전담하는 모듈입니다.
URL 직접 조회(Fetch) 및 Tavily 검색(Search)을 병렬로 처리합니다.

[UPDATE] v1.5.0
- 프리셋 기반 검색 제어 (max_queries, search_depth)
- 검색 결과 캐싱 연동
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.mcp_client import fetch_url_sync, search_sync
from tools.web_search import should_search_web
from tools.search_client import _is_blocked_domain  # [NEW] 도메인 필터링
from tools.search_cache import get_cached_search, cache_search_result, get_cache_stats  # [NEW] 캐싱


def execute_web_search(
    user_input: str,
    rag_context: str = "",
    max_queries: int = 3,      # [NEW] 최대 쿼리 수
    search_depth: str = "basic"  # [NEW] 검색 깊이 (basic/advanced)
) -> dict:
    """
    웹 검색 또는 URL 조회를 수행하고 결과를 반환합니다.

    [UPDATE] v1.5.0
    - max_queries: 프리셋 기반 쿼리 수 제한
    - search_depth: 검색 깊이 (basic=빠른, advanced=심층)
    - 캐싱: 동일 쿼리 중복 호출 방지

    Args:
        user_input: 사용자 입력 문자열
        rag_context: RAG 검색 컨텍스트 (참고용)
        max_queries: 최대 검색 쿼리 수 (기본 3)
        search_depth: 검색 깊이 - "basic" 또는 "advanced" (기본 "basic")

    Returns:
        dict: {
            "context": str | None,  # 포맷팅된 검색 결과 문자열
            "urls": List[str],      # 참조된 URL 목록
            "sources": List[dict],  # [{"title":, "url":}] 형태의 소스 목록
            "error": str | None     # 에러 발생 시 메시지
        }
    """
    web_contents = []
    web_urls = []
    web_sources = []
    error = None

    try:
        # 1. URL이 직접 제공된 경우
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, user_input)

        if urls:
            for url in urls[:3]:
                # [NEW] 차단 도메인 체크
                if _is_blocked_domain(url):
                    print(f"[INFO] 관련 없는 URL 제외: {url}")
                    continue
                    
                try:
                    content = fetch_url_sync(url, max_length=3000)
                    if content and not content.startswith("[웹 조회 실패"):
                        web_contents.append(f"[URL 참조: {url}]\n{content}")
                        web_urls.append(url)
                except Exception as e:
                    print(f"[WARN] URL 조회 실패 ({url}): {e}")
        
        # 2. URL이 없으면 조건부 웹 검색
        else:
            # [NEW] max_queries 파라미터 전달
            decision = should_search_web(user_input, rag_context if rag_context else "", max_queries=max_queries)
            print(f"[WebSearch] Decision: should_search={decision['should_search']}, reason={decision.get('reason', 'N/A')}, max_queries={max_queries}, depth={search_depth}")

            if decision["should_search"]:
                search_queries = decision["search_query"]
                
                # 리스트가 아니면 리스트로 변환 (하위 호환)
                if isinstance(search_queries, str):
                    queries = [search_queries]
                else:
                    queries = search_queries
                    
                print(f"[WebSearch] Executing Queries: {queries}")

                if queries:
                    # [Optimization] 다중 쿼리 병렬 실행 + 캐싱
                    def run_query(idx, q):
                        try:
                            # [NEW] 캐시 먼저 확인
                            cached = get_cached_search(q)
                            if cached:
                                print(f"[WebSearch] Cache HIT: {q[:30]}...")
                                return idx, q, cached

                            # 캐시 미스 → 실제 검색
                            result = search_sync(q, search_depth=search_depth)

                            # [NEW] 결과 캐싱
                            if result.get("success"):
                                cache_search_result(q, result)

                            return idx, q, result
                        except Exception as e:
                            return idx, q, {"success": False, "error": str(e)}

                    with ThreadPoolExecutor(max_workers=3) as executor:
                        futures = [executor.submit(run_query, i, q) for i, q in enumerate(queries)]
                        
                        # 순서 보장을 위해 인덱스로 정렬할 수 있도록 결과 수집
                        results = []
                        for future in as_completed(futures):
                            results.append(future.result())
                        
                        # 인덱스 순 정렬
                        results.sort(key=lambda x: x[0])
                        
                        for idx, q, search_result in results:
                            print(f"[WebSearch] Query '{q}' result: success={search_result.get('success')}, source={search_result.get('source', 'unknown')}")

                            if search_result.get("success"):
                                formatted_result = ""
                                if "results" in search_result and isinstance(search_result["results"], list):
                                    for res in search_result["results"][:5]:  # 필터링 고려하여 더 확인
                                        title = res.get("title", "제목 없음")
                                        url = res.get("url", "URL 없음")
                                        
                                        # [NEW] 차단 도메인 체크
                                        if _is_blocked_domain(url):
                                            print(f"[INFO] 관련 없는 검색 결과 제외: {url}")
                                            continue
                                        
                                        snippet = res.get("snippet", "")[:300]
                                        full_content = f"- [{title}]({url})\n  {snippet}"
                                        
                                        if url and url.startswith("http"):
                                            # 제목+URL+내용 함께 저장 (중복 제거)
                                            if not any(s.get("url") == url for s in web_sources):
                                                web_sources.append({
                                                    "title": title, 
                                                    "url": url,
                                                    "content": full_content
                                                })
                                        
                                if not web_sources and "formatted" in search_result:
                                    # 구조화된 결과가 없을 때 (fallback)
                                    web_contents.append(f"[웹 검색 결과 {idx+1} - {q}]\n{search_result['formatted']}")
                            else:
                                print(f"[WARN] 검색 실패 ({q}): {search_result.get('error')}")
                else:
                    pass

    except Exception as e:
        print(f"[WARN] 웹 조회 단계 오류: {e}")
        error = str(e)

    # 3. 결과 조합 및 제한 (최대 5개)
    # [Optimization] 출처 수와 컨텍스트 내용을 모두 5개로 제한하여 일치시킴
    MAX_SOURCES = 5
    
    # URL 직접 입력의 경우 web_contents에 이미 있음
    # 검색 결과인 경우 web_sources에서 재조합
    
    search_context_list = []
    if web_sources:
        # 중복 URL 제거 (이미 위에서 했지만 확실하게)
        seen_urls = set()
        unique_sources = []
        for src in web_sources:
            if src["url"] not in seen_urls:
                unique_sources.append(src)
                seen_urls.add(src["url"])
        
        # 5개로 자르기
        if len(unique_sources) > MAX_SOURCES:
            unique_sources = unique_sources[:MAX_SOURCES]
            
        web_sources = unique_sources
        web_urls = [s["url"] for s in web_sources]
        
        # 컨텍스트 재조합
        for i, src in enumerate(web_sources):
            search_context_list.append(src.get("content", ""))

    # 최종 컨텍스트: [URL 내용] + [검색 결과 내용(5개)]
    final_parts = web_contents + search_context_list
    final_context_str = "\n\n---\n\n".join(final_parts) if final_parts else None

    return {
        "context": final_context_str,
        "urls": web_urls,
        "sources": web_sources,
        "error": error
    }

