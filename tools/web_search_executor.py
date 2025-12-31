"""
PlanCraft Agent - Web Search Executor

웹 검색 실행 로직을 전담하는 모듈입니다.
URL 직접 조회(Fetch) 및 Tavily 검색(Search)을 병렬로 처리합니다.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tools.mcp_client import fetch_url_sync, search_sync
from tools.web_search import should_search_web

def execute_web_search(user_input: str, rag_context: str = "") -> dict:
    """
    웹 검색 또는 URL 조회를 수행하고 결과를 반환합니다.
    
    Args:
        user_input: 사용자 입력 문자열
        rag_context: RAG 검색 컨텍스트 (참고용)

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
                try:
                    content = fetch_url_sync(url, max_length=3000)
                    if content and not content.startswith("[웹 조회 실패"):
                        web_contents.append(f"[URL 참조: {url}]\n{content}")
                        web_urls.append(url)
                except Exception as e:
                    print(f"[WARN] URL 조회 실패 ({url}): {e}")
        
        # 2. URL이 없으면 조건부 웹 검색
        else:
            decision = should_search_web(user_input, rag_context if rag_context else "")
            if decision["should_search"]:
                base_query = decision["search_query"]
                
                if base_query:
                    queries = [base_query]
                    if "트렌드" in base_query:
                        queries.append(base_query.replace("트렌드", "시장 규모 통계"))
                    else:
                        queries.append(f"{base_query} 시장 규모 및 경쟁사")
                    
                    # [Optimization] 다중 쿼리 병렬 실행
                    def run_query(idx, q):
                        try:
                            return idx, q, search_sync(q)
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
                            if search_result.get("success"):
                                formatted_result = ""
                                if "results" in search_result and isinstance(search_result["results"], list):
                                    for res in search_result["results"][:3]:
                                        title = res.get("title", "제목 없음")
                                        url = res.get("url", "URL 없음")
                                        snippet = res.get("snippet", "")[:200]
                                        formatted_result += f"- [{title}]({url})\n  {snippet}\n"
                                        if url and url.startswith("http"):
                                            web_urls.append(url)
                                            # 제목+URL 함께 저장 (중복 제거)
                                            if not any(s.get("url") == url for s in web_sources):
                                                web_sources.append({"title": title, "url": url})
                                
                                if not formatted_result and "formatted" in search_result:
                                    formatted_result = search_result["formatted"]
                                    
                                web_contents.append(f"[웹 검색 결과 {idx+1} - {q}]\n{formatted_result}")
                            else:
                                print(f"[WARN] 검색 실패 ({q}): {search_result.get('error')}")
                else:
                    # 쿼리가 없는 경우 (should_search=True라도)
                    pass

    except Exception as e:
        print(f"[WARN] 웹 조회 단계 오류: {e}")
        error = str(e)

    # 3. 결과 조합
    final_context_str = None
    if web_contents:
        final_context_str = "\n\n---\n\n".join(web_contents)

    return {
        "context": final_context_str,
        "urls": web_urls,
        "sources": web_sources,
        "error": error
    }
