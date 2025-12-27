"""
MCP 동작 테스트 스크립트

실행 방법:
    python tests/test_mcp.py (루트에서)
    python test_mcp.py (tests 폴더에서)
"""

import sys
import os

# 상위 디렉토리를 path에 추가 (tests 폴더에서 실행 시)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import Config

print("=" * 50)
print("MCP 설정 확인")
print("=" * 50)
print(f"MCP_ENABLED: {Config.MCP_ENABLED}")
print(f"TAVILY_API_KEY: {'설정됨' if Config.TAVILY_API_KEY else '없음'}")
print(f"MCP_FETCH_COMMAND: {Config.MCP_FETCH_COMMAND}")
print(f"MCP_TAVILY_COMMAND: {Config.MCP_TAVILY_COMMAND}")
print()

print("=" * 50)
print("MCP Toolkit 테스트")
print("=" * 50)
from tools.mcp_client import MCPToolkit
toolkit = MCPToolkit()
print(f"use_mcp: {toolkit._use_mcp}")
print()

if toolkit._use_mcp:
    print("[INFO] MCP 모드 활성화됨")
    print("[INFO] 실제 MCP 서버 연결은 비동기 환경에서 진행됩니다")
else:
    print("[INFO] Fallback 모드 (requests + DuckDuckGo)")

print()
print("=" * 50)
print("Fallback 검색 테스트")
print("=" * 50)
result = toolkit._fallback_search("AI trend 2025", max_results=2)
print(f"검색 성공: {result['success']}")
print(f"소스: {result['source']}")
if result["success"]:
    print(f"결과 수: {len(result['results'])}개")
    for i, r in enumerate(result["results"][:2], 1):
        print(f"  [{i}] {r['title'][:50]}...")

print()
print("=" * 50)
print("테스트 완료!")
print("=" * 50)
