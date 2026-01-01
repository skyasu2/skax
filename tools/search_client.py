"""
PlanCraft Agent - Web Search Client

웹 검색 기능을 제공하는 모듈입니다.
Tavily API를 HTTP Request로 직접 호출하여 의존성을 최소화합니다.
"""

import os
import requests
from typing import List, Dict, Optional
from urllib.parse import urlparse
from utils.config import Config

# =============================================================================
# 도메인 필터링 설정 (관련 없는 사이트 제외)
# =============================================================================
# 기획서/비즈니스와 무관한 도메인 (총기류, 성인물 등)
BLOCKED_DOMAINS = [
    "ar15.com",           # 총기 관련
    "guns.com",           # 총기 관련
    "gunsamerica.com",    # 총기 관련
    "armslist.com",       # 총기 관련
    "pornhub.com",        # 성인물
    "xvideos.com",        # 성인물
    "reddit.com/r/guns",  # 총기 서브레딧
]

# 관련성 낮은 도메인 패턴 (부분 일치)
BLOCKED_PATTERNS = [
    "gun", "firearm", "weapon", "ammo", "ammunition",
    "adult", "xxx", "porn",
]


def _is_blocked_domain(url: str) -> bool:
    """
    URL이 차단 목록에 있는지 확인합니다.
    
    Args:
        url: 검사할 URL
        
    Returns:
        bool: 차단해야 하면 True
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        full_path = f"{domain}{parsed.path}".lower()
        
        # 1. 정확한 도메인 매칭
        for blocked in BLOCKED_DOMAINS:
            if blocked in domain or blocked in full_path:
                return True
        
        # 2. 패턴 매칭 (도메인 또는 경로에 포함)
        for pattern in BLOCKED_PATTERNS:
            if pattern in domain:
                return True
                
        return False
    except Exception:
        return False


class SearchClient:
    """
    웹 검색 클라이언트 (Tavily API 기반)
    """
    
    def __init__(self):
        self.api_key = Config.TAVILY_API_KEY
        self.base_url = "https://api.tavily.com/search"
        
    def search(self, query: str, max_results: int = 5) -> str:
        """
        웹 검색을 수행하고 결과를 문자열로 반환합니다.
        
        Args:
            query: 검색어
            max_results: 최대 결과 수 (필터링 후 최대 3개 반환)
            
        Returns:
            str: 마크다운 형식의 검색 결과 요약
        """
        if not self.api_key:
            return "[Web Search Skipped] TAVILY_API_KEY is not set."
            
        try:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": max_results  # 필터링 손실 고려하여 더 많이 요청
            }
            
            response = requests.post(self.base_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 답변이 있으면 우선 사용
            answer = data.get("answer", "")
            results = data.get("results", [])
            
            # [NEW] 차단 도메인 필터링
            filtered_results = []
            for res in results:
                url = res.get("url", "")
                if not _is_blocked_domain(url):
                    filtered_results.append(res)
                else:
                    print(f"[INFO] 관련 없는 도메인 제외: {url}")
            
            markdown_output = f"### 🔍 '{query}' 검색 결과\n\n"
            
            if answer:
                markdown_output += f"**AI 요약**: {answer}\n\n"
                
            markdown_output += "**상세 결과**:\n"
            for res in filtered_results[:3]:  # 필터링 후 최대 3개
                title = res.get("title", "No Title")
                url = res.get("url", "#")
                content = res.get("content", "")
                # 출처 도메인 추출
                domain = urlparse(url).netloc.replace("www.", "") if url else "출처"
                markdown_output += f"- **[{title}]({url})** ({domain}): {content[:300]}...\n"
                
            return markdown_output
            
        except Exception as e:
            return f"[Web Search Failed] Error: {str(e)}"

# 전역 인스턴스
_search_client = None

def get_search_client() -> SearchClient:
    global _search_client
    if not _search_client:
        _search_client = SearchClient()
    return _search_client

