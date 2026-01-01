"""
PlanCraft Agent - MCP Web Client 모듈

MCP(Model Context Protocol) Fetch 서버를 통해 웹 콘텐츠를 조회합니다.
langchain-mcp-adapters를 사용하여 LangChain/LangGraph와 통합합니다.

주요 기능:
    - 웹페이지 콘텐츠 fetch (HTML → Markdown 변환)
    - 여러 URL 동시 조회
    - LangChain 도구로 변환

사용 예시:
    from tools.web_client import WebClient

    client = WebClient()
    content = await client.fetch_url("https://example.com")
    print(content)
"""

import asyncio
import ipaddress
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse


# =============================================================================
# SSRF 방어: URL 검증
# =============================================================================

# 차단할 내부 호스트명
BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
}

# 허용 프로토콜
ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_url(url: str) -> bool:
    """
    URL이 안전한지 검증합니다 (SSRF 방어).

    차단 대상:
    - 내부 IP (private, loopback, link-local)
    - localhost 및 유사 호스트명
    - http/https 외의 프로토콜 (file://, ftp:// 등)

    Args:
        url: 검증할 URL

    Returns:
        bool: 안전하면 True, 위험하면 False
    """
    try:
        parsed = urlparse(url)

        # 1. 프로토콜 검증
        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            print(f"[SSRF] 차단된 프로토콜: {parsed.scheme}")
            return False

        # 2. 호스트명 검증
        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower()

        # 3. 차단된 호스트명 검사
        if hostname_lower in BLOCKED_HOSTS:
            print(f"[SSRF] 차단된 호스트: {hostname}")
            return False

        # 4. IP 주소인 경우 내부 IP 검사
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                print(f"[SSRF] 차단된 내부 IP: {hostname}")
                return False
        except ValueError:
            # 도메인명인 경우 (IP가 아님) - 허용
            pass

        # 5. 포트 검증 (선택적: 일반적인 웹 포트만 허용)
        if parsed.port and parsed.port not in {80, 443, 8080, 8443}:
            print(f"[SSRF] 비표준 포트: {parsed.port}")
            # 비표준 포트는 경고만 하고 허용 (필요시 차단으로 변경)

        return True

    except Exception as e:
        print(f"[SSRF] URL 파싱 오류: {e}")
        return False


class WebClient:
    """
    MCP Fetch 서버를 사용한 웹 콘텐츠 조회 클라이언트

    MCP 프로토콜을 통해 웹페이지를 가져오고 마크다운으로 변환합니다.
    LangChain 에이전트와 통합하여 실시간 웹 정보를 활용할 수 있습니다.

    Attributes:
        _client: MultiServerMCPClient 인스턴스
        _tools: 로드된 MCP 도구 목록

    Example:
        >>> client = WebClient()
        >>> await client.initialize()
        >>> content = await client.fetch_url("https://example.com")
    """

    def __init__(self, use_mcp: bool = None):
        """
        WebClient를 초기화합니다.
        
        Args:
            use_mcp: MCP 프로토콜 사용 여부 (None이면 Config에서 결정)
        """
        from utils.config import Config
        
        self._client = None
        self._tools = None
        self._initialized = False
        self._use_mcp = use_mcp if use_mcp is not None else Config.MCP_ENABLED
        
        if self._use_mcp:
            print("[INFO] MCP 모드 활성화 (MCP_ENABLED=true)")
        else:
            print("[INFO] Fallback 모드 (MCP_ENABLED=false)")

    async def initialize(self) -> bool:
        """
        MCP Fetch 서버에 연결합니다.

        Returns:
            bool: 초기화 성공 여부

        Note:
            - MCP_ENABLED=true일 때만 MCP 서버 연결을 시도합니다.
            - MCP_ENABLED=false면 Fallback 모드로 바로 동작합니다.
        """
        # MCP 비활성화 시 바로 Fallback 모드
        if not self._use_mcp:
            print("[INFO] MCP 비활성화 - Fallback 모드로 동작")
            return False
        
        # MCP 활성화 시 서버 연결 시도
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            from utils.config import Config

            # MCP Fetch 서버 설정 (환경변수에서 읽음)
            self._client = MultiServerMCPClient({
                "fetch": {
                    "command": Config.MCP_FETCH_COMMAND,
                    "args": [Config.MCP_FETCH_SERVER],
                    "transport": "stdio",
                }
            })

            # 도구 로드
            self._tools = await self._client.get_tools()
            self._initialized = True
            print("✅ MCP Fetch 서버 연결 완료")
            return True

        except ImportError:
            print("⚠️ langchain-mcp-adapters 패키지가 설치되지 않았습니다")
            print("  → pip install langchain-mcp-adapters")
            self._initialized = False
            return False
            
        except Exception as e:
            print(f"⚠️ MCP Fetch 서버 연결 실패: {e}")
            print("  → Fallback 모드로 전환합니다 (requests 사용)")
            self._initialized = False
            return False

    async def fetch_url(self, url: str, max_length: int = 5000) -> str:
        """
        URL에서 웹 콘텐츠를 가져옵니다.

        Args:
            url: 조회할 URL
            max_length: 반환할 최대 문자 수

        Returns:
            str: 마크다운으로 변환된 웹 콘텐츠

        Example:
            >>> content = await client.fetch_url("https://news.example.com")
            >>> print(content[:500])
        """
        # MCP 서버 사용 가능 시
        if self._initialized and self._tools:
            try:
                # fetch 도구 찾기
                fetch_tool = next(
                    (t for t in self._tools if t.name == "fetch"),
                    None
                )
                if fetch_tool:
                    result = await fetch_tool.ainvoke({"url": url})
                    return result[:max_length] if len(result) > max_length else result
            except Exception as e:
                print(f"⚠️ MCP fetch 실패: {e}")

        # Fallback: requests 사용
        return await self._fallback_fetch(url, max_length)

    async def _fallback_fetch(self, url: str, max_length: int = 5000) -> str:
        """
        requests를 사용한 fallback fetch

        Args:
            url: 조회할 URL
            max_length: 반환할 최대 문자 수

        Returns:
            str: 추출된 텍스트 콘텐츠
        """
        try:
            # [보안] SSRF 방어: URL 검증
            if not _is_safe_url(url):
                return "[보안 오류: 접근할 수 없는 URL입니다]"

            import requests
            from bs4 import BeautifulSoup

            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; PlanCraftBot/1.0)"
            }

            response = requests.get(url, headers=headers, timeout=10, verify=True)
            response.raise_for_status()

            # HTML 파싱
            soup = BeautifulSoup(response.text, 'html.parser')

            # 스크립트, 스타일 제거
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            # 텍스트 추출
            text = soup.get_text(separator='\n', strip=True)

            # 빈 줄 정리
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            content = '\n'.join(lines)

            return content[:max_length] if len(content) > max_length else content

        except Exception as e:
            return f"[웹 조회 실패: {str(e)}]"

    async def fetch_multiple(self, urls: List[str], max_length: int = 3000) -> Dict[str, str]:
        """
        여러 URL을 동시에 조회합니다.

        Args:
            urls: 조회할 URL 목록
            max_length: 각 URL당 최대 문자 수

        Returns:
            Dict[str, str]: URL -> 콘텐츠 매핑

        Example:
            >>> urls = ["https://a.com", "https://b.com"]
            >>> results = await client.fetch_multiple(urls)
        """
        tasks = [self.fetch_url(url, max_length) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            url: (str(result) if isinstance(result, Exception) else result)
            for url, result in zip(urls, results)
        }

    def get_tools(self) -> List[Any]:
        """
        LangChain 호환 도구 목록을 반환합니다.

        Returns:
            List: LangChain Tool 객체 목록
        """
        if self._tools:
            return self._tools
        return []

    async def close(self):
        """MCP 클라이언트 연결을 종료합니다."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except:
                pass
        self._initialized = False


# =============================================================================
# 동기 래퍼 함수 (비동기 지원하지 않는 환경용)
# =============================================================================

def fetch_url_sync(url: str, max_length: int = 5000) -> str:
    """
    URL에서 웹 콘텐츠를 동기적으로 가져옵니다.

    비동기를 지원하지 않는 환경에서 사용합니다.
    내부적으로 requests를 직접 사용합니다.

    Args:
        url: 조회할 URL
        max_length: 반환할 최대 문자 수

    Returns:
        str: 추출된 텍스트 콘텐츠

    Example:
        >>> content = fetch_url_sync("https://example.com")
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PlanCraftBot/1.0)"
        }

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


# =============================================================================
# 전역 클라이언트 인스턴스
# =============================================================================
_web_client: Optional[WebClient] = None


async def get_web_client() -> WebClient:
    """
    전역 WebClient 인스턴스를 반환합니다.

    싱글톤 패턴으로 하나의 클라이언트만 유지합니다.

    Returns:
        WebClient: 초기화된 웹 클라이언트
    """
    global _web_client

    if _web_client is None:
        _web_client = WebClient()
        await _web_client.initialize()

    return _web_client
