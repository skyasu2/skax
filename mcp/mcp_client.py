"""
PlanCraft Agent - MCP 통합 클라이언트

2개의 MCP 서버를 통합 관리합니다:
1. mcp-server-fetch: URL 콘텐츠 가져오기 (uvx)
2. tavily-mcp: AI 웹 검색 (npx)

사용 예시:
    from mcp.mcp_client import MCPToolkit
    
    toolkit = MCPToolkit()
    await toolkit.initialize()
    
    # URL Fetch
    content = await toolkit.fetch_url("https://example.com")
    
    # 웹 검색
    results = await toolkit.search("AI 트렌드 2025")
"""

import os
import asyncio
from typing import Optional, List, Dict, Any


class MCPToolkit:
    """
    MCP 통합 도구 모음
    
    여러 MCP 서버를 하나의 인터페이스로 통합 관리합니다.
    MCP_ENABLED=false면 Fallback 모드로 동작합니다.
    """
    
    def __init__(self, use_mcp: bool = None):
        """
        MCPToolkit 초기화
        
        Args:
            use_mcp: MCP 사용 여부 (None이면 Config에서 결정)
        """
        from utils.config import Config
        
        self._client = None
        self._tools = {}
        self._initialized = False
        self._use_mcp = use_mcp if use_mcp is not None else Config.MCP_ENABLED
        
    async def initialize(self) -> bool:
        """
        MCP 서버들에 연결합니다.
        
        Returns:
            bool: 초기화 성공 여부
        """
        if not self._use_mcp:
            print("[INFO] MCP 비활성화 - Fallback 모드로 동작")
            return False
        
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            from utils.config import Config
            
            # API 키 검증
            if not Config.TAVILY_API_KEY:
                print("⚠️ TAVILY_API_KEY가 설정되지 않았습니다")
                return False
            
            # 2개의 MCP 서버 설정
            server_config = {
                # 1. URL Fetch 서버 (Python - uvx)
                "fetch": {
                    "command": Config.MCP_FETCH_COMMAND,
                    "args": [Config.MCP_FETCH_SERVER],
                    "transport": "stdio",
                },
                # 2. Tavily 검색 서버 (Node.js - npx)
                "tavily": {
                    "command": Config.MCP_TAVILY_COMMAND,
                    "args": ["-y", Config.MCP_TAVILY_SERVER],
                    "transport": "stdio",
                    "env": {
                        "TAVILY_API_KEY": Config.TAVILY_API_KEY
                    }
                }
            }
            
            print("[INFO] MCP 서버 연결 중...")
            print(f"  - Fetch: {Config.MCP_FETCH_COMMAND} {Config.MCP_FETCH_SERVER}")
            print(f"  - Tavily: {Config.MCP_TAVILY_COMMAND} {Config.MCP_TAVILY_SERVER}")
            
            self._client = MultiServerMCPClient(server_config)
            
            # 모든 도구 로드
            all_tools = await self._client.get_tools()
            
            # 도구를 이름별로 분류
            for tool in all_tools:
                self._tools[tool.name] = tool
            
            self._initialized = True
            print(f"✅ MCP 연결 완료 - {len(all_tools)}개 도구 로드됨")
            print(f"  도구 목록: {list(self._tools.keys())}")
            
            return True
            
        except ImportError:
            print("⚠️ langchain-mcp-adapters 패키지가 설치되지 않았습니다")
            print("  → pip install langchain-mcp-adapters")
            return False
            
        except Exception as e:
            print(f"⚠️ MCP 서버 연결 실패: {e}")
            print("  → Fallback 모드로 전환")
            self._initialized = False
            return False
    
    async def fetch_url(self, url: str, max_length: int = 5000) -> str:
        """
        URL에서 콘텐츠를 가져옵니다.
        
        Args:
            url: 조회할 URL
            max_length: 최대 문자 수
            
        Returns:
            str: 웹 콘텐츠
        """
        # MCP 사용 가능 시
        if self._initialized and "fetch" in self._tools:
            try:
                result = await self._tools["fetch"].ainvoke({"url": url})
                content = str(result)
                return content[:max_length] if len(content) > max_length else content
            except Exception as e:
                print(f"⚠️ MCP fetch 실패: {e}")
        
        # Fallback: requests 사용
        return self._fallback_fetch(url, max_length)
    
    async def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        웹 검색을 수행합니다.
        
        Args:
            query: 검색 쿼리
            max_results: 최대 결과 수
            
        Returns:
            Dict: 검색 결과
        """
        # MCP 사용 가능 시 - Tavily 도구 찾기
        if self._initialized:
            # Tavily 도구 이름 찾기 (tavily_search, search 등)
            tavily_tool = None
            for name, tool in self._tools.items():
                if "tavily" in name.lower() or "search" in name.lower():
                    tavily_tool = tool
                    break
            
            if tavily_tool:
                try:
                    result = await tavily_tool.ainvoke({"query": query})
                    return {
                        "success": True,
                        "query": query,
                        "results": result,
                        "source": "tavily-mcp"
                    }
                except Exception as e:
                    print(f"⚠️ Tavily 검색 실패: {e}")
        
        # Fallback: DuckDuckGo 사용
        return self._fallback_search(query, max_results)
    
    def _fallback_fetch(self, url: str, max_length: int = 5000) -> str:
        """Fallback: requests로 URL fetch"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {"User-Agent": "Mozilla/5.0 (compatible; PlanCraftBot/1.0)"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            content = '\n'.join(lines)
            
            return content[:max_length] if len(content) > max_length else content
            
        except Exception as e:
            return f"[웹 조회 실패: {str(e)}]"
    
    def _fallback_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Fallback 검색 (MCP 실패 시)
        
        DuckDuckGo 제거됨 - MCP(Tavily) 전용
        MCP 연결 실패 시 빈 결과 반환
        """
        return {
            "success": False,
            "query": query,
            "results": [],
            "formatted": "[웹 검색 사용 불가 - MCP 연결 필요]",
            "error": "MCP not initialized. Set MCP_ENABLED=true and ensure Tavily API key is configured.",
            "source": "no-search-available"
        }
    
    def get_tools(self) -> List[Any]:
        """로드된 MCP 도구 목록 반환"""
        return list(self._tools.values())
    
    async def close(self):
        """MCP 연결 종료"""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except:
                pass
        self._initialized = False


# =============================================================================
# 전역 인스턴스
# =============================================================================

_mcp_toolkit: Optional[MCPToolkit] = None


async def get_mcp_toolkit() -> MCPToolkit:
    """전역 MCPToolkit 인스턴스 반환 (싱글톤)"""
    global _mcp_toolkit
    
    if _mcp_toolkit is None:
        _mcp_toolkit = MCPToolkit()
        await _mcp_toolkit.initialize()
    
    return _mcp_toolkit


# =============================================================================
# 동기 래퍼 함수 (Streamlit 등 비동기 미지원 환경용)
# =============================================================================

def fetch_url_sync(url: str, max_length: int = 5000) -> str:
    """동기적으로 URL fetch (Fallback 사용)"""
    toolkit = MCPToolkit(use_mcp=False)  # 동기 환경에서는 Fallback 사용
    return toolkit._fallback_fetch(url, max_length)


def search_sync(query: str, max_results: int = 5) -> Dict[str, Any]:
    """동기적으로 웹 검색 (Fallback 사용)"""
    toolkit = MCPToolkit(use_mcp=False)
    return toolkit._fallback_search(query, max_results)
