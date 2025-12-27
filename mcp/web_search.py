"""
PlanCraft Agent - MCP 웹 검색 모듈

DuckDuckGo를 사용한 무료 웹 검색 기능을 제공합니다.
조건부로 호출되어 최신 정보가 필요한 경우에만 사용됩니다.

주요 기능:
    - DuckDuckGo 웹 검색 (무료, API 키 불필요)
    - 검색 결과 요약 및 포맷팅
    - 조건부 검색 판단 로직

사용 예시:
    from mcp.web_search import search_web, should_search_web

    # 웹 검색 필요 여부 판단
    if should_search_web(user_input):
        results = search_web("AI 헬스케어 트렌드 2025")
        print(results)
"""

import re
from typing import List, Dict, Optional
from datetime import datetime


# =============================================================================
# 웹 검색 필요 여부 판단 키워드
# =============================================================================

# 최신 정보가 필요함을 나타내는 키워드
RECENCY_KEYWORDS = [
    # 시간 관련
    "최근", "최신", "요즘", "현재", "지금", "올해", "이번",
    "2024", "2025", "2026",
    "트렌드", "동향", "현황", "전망",
    # 영어
    "recent", "latest", "current", "trend", "now",
]

# 외부 정보가 필요함을 나타내는 키워드
EXTERNAL_KEYWORDS = [
    # 시장/경쟁
    "시장", "경쟁사", "경쟁", "업계", "산업",
    "사례", "벤치마크", "레퍼런스",
    # 기술
    "기술", "신기술", "혁신", "AI", "인공지능",
    # 통계
    "통계", "데이터", "수치", "규모",
    # 영어
    "market", "competitor", "industry", "case study",
]

# 내부 문서로 충분한 키워드 (웹 검색 불필요)
INTERNAL_KEYWORDS = [
    "규정", "매뉴얼", "절차", "프로세스", "내부",
    "사내", "우리", "당사", "회사",
]


def should_search_web(user_input: str, rag_context: str = "") -> Dict[str, any]:
    """
    웹 검색이 필요한지 판단합니다.

    조건부 판단 로직:
    1. 최신성 키워드가 있으면 → 검색 필요
    2. 외부 정보 키워드가 있으면 → 검색 필요
    3. 내부 문서 키워드만 있으면 → 검색 불필요
    4. RAG 컨텍스트가 충분하면 → 검색 불필요

    Args:
        user_input: 사용자 입력 텍스트
        rag_context: RAG에서 검색된 컨텍스트

    Returns:
        Dict: {
            "should_search": bool,
            "reason": str,
            "search_query": str (검색 필요시)
        }

    Example:
        >>> result = should_search_web("AI 헬스케어 최신 트렌드")
        >>> print(result)
        {"should_search": True, "reason": "최신 정보 필요", "search_query": "AI 헬스케어 트렌드 2025"}
    """
    input_lower = user_input.lower()

    # 1. URL이 이미 있으면 웹 검색 불필요 (URL fetch로 처리)
    if re.search(r'https?://', user_input):
        return {
            "should_search": False,
            "reason": "URL이 직접 제공됨",
            "search_query": None
        }

    # 2. 내부 문서 키워드가 있으면 검색 불필요
    has_internal = any(kw in user_input for kw in INTERNAL_KEYWORDS)
    if has_internal and not any(kw in user_input for kw in RECENCY_KEYWORDS):
        return {
            "should_search": False,
            "reason": "내부 문서 질의",
            "search_query": None
        }

    # 3. 최신성 키워드 체크
    has_recency = any(kw in input_lower for kw in RECENCY_KEYWORDS)
    if has_recency:
        query = _generate_search_query(user_input, "recency")
        return {
            "should_search": True,
            "reason": "최신 정보 필요",
            "search_query": query
        }

    # 4. 외부 정보 키워드 체크
    has_external = any(kw in input_lower for kw in EXTERNAL_KEYWORDS)
    if has_external:
        query = _generate_search_query(user_input, "external")
        return {
            "should_search": True,
            "reason": "외부 시장/기술 정보 필요",
            "search_query": query
        }

    # 5. RAG 컨텍스트가 충분하면 검색 불필요
    if rag_context and len(rag_context) > 500:
        return {
            "should_search": False,
            "reason": "RAG 컨텍스트 충분",
            "search_query": None
        }

    # 6. 기본값: 검색 불필요
    return {
        "should_search": False,
        "reason": "내부 지식으로 충분",
        "search_query": None
    }


def _generate_search_query(user_input: str, query_type: str) -> str:
    """
    검색 쿼리를 생성합니다.

    Args:
        user_input: 사용자 입력
        query_type: 쿼리 타입 ("recency" 또는 "external")

    Returns:
        str: 최적화된 검색 쿼리
    """
    # 불필요한 조사/어미 제거
    clean_input = re.sub(r'[을를이가은는에서의로]', ' ', user_input)
    clean_input = re.sub(r'\s+', ' ', clean_input).strip()

    # 너무 긴 경우 핵심 단어만 추출
    words = clean_input.split()
    if len(words) > 10:
        # 명사 위주로 추출 (간단한 휴리스틱)
        important_words = [w for w in words if len(w) > 1][:7]
        clean_input = ' '.join(important_words)

    # 현재 연도 추가 (최신성 쿼리)
    current_year = datetime.now().year
    if query_type == "recency" and str(current_year) not in clean_input:
        clean_input = f"{clean_input} {current_year}"

    return clean_input


def search_web(query: str, max_results: int = 5) -> Dict[str, any]:
    """
    DuckDuckGo로 웹 검색을 수행합니다.

    Args:
        query: 검색 쿼리
        max_results: 최대 결과 수

    Returns:
        Dict: {
            "success": bool,
            "query": str,
            "results": List[Dict],  # [{title, url, snippet}]
            "formatted": str,  # 포맷팅된 텍스트
            "source": "duckduckgo"
        }

    Example:
        >>> result = search_web("AI 헬스케어 트렌드 2025")
        >>> print(result["formatted"])
    """
    try:
        from duckduckgo_search import DDGS

        results = []
        formatted_parts = []

        with DDGS() as ddgs:
            search_results = list(ddgs.text(query, max_results=max_results))

            for i, r in enumerate(search_results, 1):
                result_item = {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                }
                results.append(result_item)

                # 포맷팅
                formatted_parts.append(
                    f"[{i}] {result_item['title']}\n"
                    f"    URL: {result_item['url']}\n"
                    f"    {result_item['snippet'][:200]}..."
                )

        formatted = "\n\n".join(formatted_parts) if formatted_parts else "검색 결과 없음"

        return {
            "success": True,
            "query": query,
            "results": results,
            "formatted": formatted,
            "source": "duckduckgo"
        }

    except ImportError:
        # duckduckgo-search 미설치 시 fallback
        return _fallback_search(query, max_results)

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "results": [],
            "formatted": f"[검색 실패: {str(e)}]",
            "source": "error"
        }


def _fallback_search(query: str, max_results: int = 5) -> Dict[str, any]:
    """
    DuckDuckGo Instant Answer API를 사용한 Fallback 검색

    Args:
        query: 검색 쿼리
        max_results: 최대 결과 수

    Returns:
        Dict: 검색 결과
    """
    try:
        import requests

        # DuckDuckGo Instant Answer API (무료, 제한적)
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        results = []
        formatted_parts = []

        # Abstract (요약)
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", "요약"),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("Abstract", "")
            })
            formatted_parts.append(
                f"[요약] {data.get('Heading', '')}\n"
                f"    {data.get('Abstract', '')}"
            )

        # Related Topics
        for i, topic in enumerate(data.get("RelatedTopics", [])[:max_results], 1):
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:50],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", "")
                })
                formatted_parts.append(
                    f"[{i}] {topic.get('Text', '')[:200]}"
                )

        formatted = "\n\n".join(formatted_parts) if formatted_parts else "관련 정보를 찾을 수 없습니다."

        return {
            "success": len(results) > 0,
            "query": query,
            "results": results,
            "formatted": formatted,
            "source": "duckduckgo_instant"
        }

    except Exception as e:
        return {
            "success": False,
            "query": query,
            "results": [],
            "formatted": f"[Fallback 검색 실패: {str(e)}]",
            "source": "error"
        }


# =============================================================================
# 통합 검색 함수 (워크플로우용)
# =============================================================================

def conditional_web_search(user_input: str, rag_context: str = "") -> Dict[str, any]:
    """
    조건부 웹 검색을 수행합니다.

    워크플로우에서 사용하는 통합 함수입니다.
    필요 여부를 판단하고, 필요시에만 검색을 수행합니다.

    Args:
        user_input: 사용자 입력
        rag_context: RAG 컨텍스트

    Returns:
        Dict: {
            "searched": bool,
            "reason": str,
            "context": str (검색 결과 또는 빈 문자열)
        }

    Example:
        >>> result = conditional_web_search("AI 헬스케어 최신 동향")
        >>> if result["searched"]:
        ...     print(f"검색 이유: {result['reason']}")
        ...     print(result["context"])
    """
    # 1. 검색 필요 여부 판단
    decision = should_search_web(user_input, rag_context)

    if not decision["should_search"]:
        return {
            "searched": False,
            "reason": decision["reason"],
            "context": ""
        }

    # 2. 웹 검색 수행
    search_result = search_web(decision["search_query"])

    if search_result["success"]:
        context = (
            f"[웹 검색 결과 - {decision['reason']}]\n"
            f"검색어: {decision['search_query']}\n"
            f"출처: {search_result['source']}\n\n"
            f"{search_result['formatted']}"
        )
        return {
            "searched": True,
            "reason": decision["reason"],
            "context": context
        }
    else:
        return {
            "searched": False,
            "reason": f"검색 실패: {search_result['formatted']}",
            "context": ""
        }
