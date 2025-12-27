"""
PlanCraft Agent - MCP 통합 클라이언트

2개의 MCP 서버를 통합 관리합니다:
1. mcp-server-fetch: URL 콘텐츠 가져오기 (uvx)
2. tavily-mcp: AI 웹 검색 (npx)

사용 예시:
    from tools.mcp_client import MCPToolkit
    
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
        
        Node.js/uvx 환경이 없는 경우(서버 등) 자동으로
        Tavily Python SDK 모드로 동작하도록 처리합니다.
        
        Returns:
            bool: 초기화 성공 여부
        """
        if not self._use_mcp:
            print("[INFO] MCP 비활성화 - Fallback 모드로 동작")
            return False
            
        # uvx 및 npx 확인
        import shutil
        has_uvx = shutil.which("uvx") is not None
        has_npx = shutil.which("npx") is not None
        
        # 둘 다 없으면 MCP 연결 시도하지 않고 바로 SDK 모드 사용
        if not has_uvx and not has_npx:
            print("[INFO] uvx/npx 미감지 - Tavily Python SDK 모드로 동작")
            # _initialized를 True로 설정하여 search() 메서드가 호출되도록 함
            # search() 내부에서 SDK로 분기됨
            self._initialized = True 
            return True
        
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            from utils.config import Config
            
            # API 키 검증
            if not Config.TAVILY_API_KEY:
                print("⚠️ TAVILY_API_KEY가 설정되지 않았습니다")
                return False
            
            # MCP 서버 설정 구성
            server_config = {}
            
            # 1. URL Fetch 서버 (uvx 필요)
            if has_uvx:
                server_config["fetch"] = {
                    "command": Config.MCP_FETCH_COMMAND,
                    "args": [Config.MCP_FETCH_SERVER],
                    "transport": "stdio",
                }
            
            # 2. Tavily 검색 서버 (npx 필요)
            if has_npx:
                server_config["tavily"] = {
                    "command": Config.MCP_TAVILY_COMMAND,
                    "args": ["-y", Config.MCP_TAVILY_SERVER],
                    "transport": "stdio",
                    "env": {
                        "TAVILY_API_KEY": Config.TAVILY_API_KEY
                    }
                }
            
            # 연결할 서버가 없으면 SDK 모드
            if not server_config:
                 print("[INFO] 실행 가능한 MCP 서버 없음 - SDK 모드로 동작")
                 self._initialized = True
                 return True

            print(f"[INFO] MCP 서버 연결 중... ({list(server_config.keys())})")
            
            self._client = MultiServerMCPClient(server_config)
            
            # 모든 도구 로드
            all_tools = await self._client.get_tools()
            
            # 도구를 이름별로 분류
            for tool in all_tools:
                self._tools[tool.name] = tool
            
            self._initialized = True
            print(f"✅ MCP 연결 완료 - {len(all_tools)}개 도구 로드됨")
            
            return True
            
        except ImportError:
            print("⚠️ langchain-mcp-adapters 패키지가 설치되지 않았습니다")
            # 패키지 없어도 SDK는 동작 가능
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"⚠️ MCP 서버 연결 실패: {e}")
            print("  → SDK/Fallback 모드로 전환")
            # 실패해도 SDK 시도를 위해 True로 설정
            self._initialized = True
            return True
    
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
        Tavily Python SDK를 사용한 웹 검색
        
        MCP 없이도 Tavily API로 직접 검색합니다.
        """
        try:
            from tavily import TavilyClient
            from utils.config import Config
            
            if not Config.TAVILY_API_KEY:
                return {
                    "success": False,
                    "query": query,
                    "results": [],
                    "error": "TAVILY_API_KEY not configured",
                    "source": "no-api-key"
                }
            
            # Tavily 클라이언트 생성
            client = TavilyClient(api_key=Config.TAVILY_API_KEY)
            
            # 검색 수행
            response = client.search(query, max_results=max_results)
            
            # 결과 포맷팅
            results = []
            formatted_parts = []
            
            for i, result in enumerate(response.get("results", [])[:max_results], 1):
                result_item = {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "snippet": result.get("content", "")[:300]
                }
                results.append(result_item)
                formatted_parts.append(
                    f"[{i}] {result_item['title']}\n"
                    f"    URL: {result_item['url']}\n"
                    f"    {result_item['snippet']}..."
                )
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "formatted": "\n\n".join(formatted_parts),
                "source": "tavily-python-sdk"
            }
            
        except ImportError:
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": "tavily-python not installed. Run: pip install tavily-python",
                "source": "import-error"
            }
        except Exception as e:
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": str(e),
                "source": "tavily-error"
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

def _run_async(coro):
    """
    비동기 코루틴을 동기적으로 실행합니다.
    Streamlit 등 이미 이벤트 루프가 있는 환경에서도 동작합니다.
    """
    import asyncio
    
    try:
        # 이미 실행 중인 이벤트 루프가 있는지 확인
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 이벤트 루프가 없으면 새로 생성
        loop = None
    
    if loop and loop.is_running():
        # Streamlit 등에서 이미 루프가 실행 중인 경우
        # nest_asyncio로 중첩 실행 허용
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.get_event_loop().run_until_complete(coro)
        except ImportError:
            # nest_asyncio 없으면 새 스레드에서 실행
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=30)
    else:
        # 이벤트 루프가 없으면 일반적인 asyncio.run 사용
        return asyncio.run(coro)


def fetch_url_sync(url: str, max_length: int = 5000) -> str:
    """
    동기적으로 URL fetch
    
    MCP 모드: 비동기 MCP 호출을 동기로 변환
    Fallback 모드: requests 직접 사용
    """
    from utils.config import Config
    
    if Config.MCP_ENABLED:
        try:
            async def _async_fetch():
                toolkit = MCPToolkit()
                await toolkit.initialize()
                return await toolkit.fetch_url(url, max_length)
            
            return _run_async(_async_fetch())
        except Exception as e:
            print(f"[WARN] MCP fetch 실패, Fallback 사용: {e}")
    
    # Fallback: requests 직접 사용
    toolkit = MCPToolkit(use_mcp=False)
    return toolkit._fallback_fetch(url, max_length)


def search_sync(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    동기적으로 웹 검색
    
    MCP 모드: 비동기 Tavily MCP 호출을 동기로 변환
    Fallback 모드: 빈 결과 반환 (DuckDuckGo 제거됨)
    """
    from utils.config import Config
    
    if Config.MCP_ENABLED:
        try:
            async def _async_search():
                toolkit = MCPToolkit()
                await toolkit.initialize()
                return await toolkit.search(query, max_results)
            
            return _run_async(_async_search())
        except Exception as e:
            print(f"[WARN] MCP 검색 실패: {e}")
            return {
                "success": False,
                "query": query,
                "results": [],
                "error": str(e),
                "source": "mcp-error"
            }
    
    # Fallback: 빈 결과 반환
    toolkit = MCPToolkit(use_mcp=False)
    return toolkit._fallback_search(query, max_results)
