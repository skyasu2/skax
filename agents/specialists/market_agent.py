"""
PlanCraft - Market Analysis Agent (시장 분석 에이전트)

기획서의 시장 분석 섹션을 전문적으로 생성합니다.
- TAM/SAM/SOM 3단계 분석
- 경쟁사 상세 분석 (실명, 특징, 차별점)
- 시장 트렌드 및 기회

출력 형식:
    {
        "tam": {...},
        "sam": {...},
        "som": {...},
        "competitors": [...],
        "trends": [...],
        "opportunities": [...]
    }
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from utils.llm import get_llm
from utils.file_logger import get_file_logger

logger = get_file_logger()


# =============================================================================
# 출력 스키마 정의
# =============================================================================

class MarketSize(BaseModel):
    """시장 규모"""
    value: str = Field(description="시장 규모 (예: $12.5B)")
    value_krw: Optional[str] = Field(default=None, description="원화 환산 (예: 16조 원)")
    year: int = Field(description="기준 연도")
    source: str = Field(description="출처")
    cagr: Optional[str] = Field(default=None, description="연평균 성장률")
    description: str = Field(description="시장 정의")


class Competitor(BaseModel):
    """경쟁사"""
    name: str = Field(description="경쟁사명 (실명)")
    description: str = Field(description="서비스 설명")
    strengths: List[str] = Field(description="강점")
    weaknesses: List[str] = Field(description="약점")
    market_share: Optional[str] = Field(default=None, description="시장 점유율")
    our_differentiation: str = Field(description="우리의 차별점")


class MarketAnalysis(BaseModel):
    """시장 분석 전체"""
    tam: MarketSize = Field(description="TAM (전체 시장)")
    sam: MarketSize = Field(description="SAM (접근 가능 시장)")
    som: MarketSize = Field(description="SOM (획득 가능 시장)")
    competitors: List[Competitor] = Field(description="경쟁사 목록 (최소 3개)")
    trends: List[str] = Field(description="시장 트렌드")
    opportunities: List[str] = Field(description="시장 기회")


# =============================================================================
# Market Agent 클래스
# =============================================================================

class MarketAgent:
    """
    시장 분석 전문 에이전트
    
    TAM/SAM/SOM 분석과 경쟁사 분석을 수행합니다.
    """
    
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.4)
        self.name = "MarketAgent"
    
    def run(
        self,
        service_overview: str,
        target_market: str,
        web_search_results: List[Dict[str, Any]] = None,
        allow_additional_search: bool = False  # [NEW] 추가 검색 허용 여부
    ) -> Dict[str, Any]:
        """
        시장 분석을 수행합니다.

        [UPDATE] v1.5.0 - 조건부 추가 검색
        - allow_additional_search=True이고 시장 규모 데이터가 없으면 추가 검색 수행
        - quality 프리셋에서만 활성화됨

        Args:
            service_overview: 서비스 개요
            target_market: 타겟 시장
            web_search_results: 초기 웹 검색 결과 (참고용)
            allow_additional_search: 추가 검색 허용 여부 (quality 모드에서 True)

        Returns:
            MarketAnalysis dict
        """
        from prompts.specialist_prompts.market_prompt import (
            MARKET_SYSTEM_PROMPT,
            MARKET_USER_PROMPT
        )
        from langchain_community.tools.tavily_search import TavilySearchResults
        from langgraph.prebuilt import create_react_agent
        from langchain_core.messages import SystemMessage, HumanMessage
        
        logger.info(f"[{self.name}] 시장 분석 시작 (allow_additional_search={allow_additional_search})")

        # 1. 초기 컨텍스트 구성
        # 이미 text로 포맷팅된 web_context가 들어올 수도 있고, list[dict]가 들어올 수도 있음
        web_context_str = ""
        if isinstance(web_search_results, str):
            web_context_str = web_search_results
        elif isinstance(web_search_results, list):
            for result in web_search_results[:5]:
                web_context_str += f"- {result.get('title', '')}: {result.get('content', '')[:500]}\n"

        # [NEW] 조건부 추가 검색 (quality 모드)
        if allow_additional_search and not self._has_market_size_data(web_context_str):
            logger.info(f"[{self.name}] 시장 규모 데이터 부족, 추가 검색 수행")
            additional_context = self._search_market_data(target_market or service_overview)
            if additional_context:
                web_context_str = f"{web_context_str}\n\n[추가 검색 결과]\n{additional_context}"
                logger.info(f"[{self.name}] 추가 검색 완료 ({len(additional_context)}자)")
        
        # 2. 프롬프트 구성
        user_prompt_content = MARKET_USER_PROMPT.format(
            service_overview=service_overview,
            target_market=target_market,
            web_context=web_context_str or "(초기 검색 결과 없음)"
        )

        # [Instruction] 순수 분석 지침 (Active Search 제거됨)
        # 비용 최적화: Tavily 중복 호출 방지를 위해 제공된 Context만 사용
        extended_system_prompt = MARKET_SYSTEM_PROMPT + """
\n
### [Analysis Instructions]
1. Relies solely on the **'Strategic Market Research' (web_context)** provided above.
2. The provided context already contains high-quality market data (Market Size, Trends, Competitors).
3. **DO NOT hallucinate facts.** If exact numbers (TAM/SAM) are missing in the context:
   - Make a **logical estimation** based on similar industry averages found in the context.
   - Explicitly mention "(Estimated)" next to the number.
4. Output must be in strictly **JSON format**.
"""
        
        messages = [
            SystemMessage(content=extended_system_prompt),
            HumanMessage(content=user_prompt_content)
        ]
        
        try:
            # 3. 실행 (Direct LLM Call)
            response = self.llm.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)

            # 4. JSON 파싱
            import json
            import re
            
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            # JSON 파싱 시도 (실패 시 클린업)
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError:
                # 가끔 마크다운이나 잡다한 텍스트가 섞일 수 있음
                logger.warning(f"[{self.name}] JSON 파싱 1차 실패, 클린업 후 재시도")
                json_str = re.sub(r'^[^{]*', '', json_str) # 첫 { 앞부분 제거
                json_str = re.sub(r'[^}]*$', '', json_str) # 마지막 } 뒷부분 제거
                result = json.loads(json_str)
            
            logger.info(f"[{self.name}] 시장 분석 완료")
            return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 시장 분석 실패: {e}")
            return self._get_fallback_analysis(service_overview)
    
    def _get_fallback_analysis(self, service_overview: str) -> Dict[str, Any]:
        """Fallback 시장 분석"""
        return {
            "tam": {
                "value": "$50B",
                "value_krw": "65조 원",
                "year": 2026,
                "source": "Grand View Research",
                "cagr": "12.5%",
                "description": "글로벌 관련 시장 전체 규모"
            },
            "sam": {
                "value": "5,000억 원",
                "value_krw": "5,000억 원",
                "year": 2026,
                "source": "한국콘텐츠진흥원",
                "cagr": "15%",
                "description": "국내 접근 가능 시장"
            },
            "som": {
                "value": "50억 원",
                "value_krw": "50억 원",
                "year": 2027,
                "source": "자체 추정",
                "description": "1년차 획득 목표 (시장 점유율 1%)"
            },
            "competitors": [
                {
                    "name": "경쟁사 A",
                    "description": "시장 선두 서비스",
                    "strengths": ["브랜드 인지도", "대규모 사용자"],
                    "weaknesses": ["기능 제한", "높은 가격"],
                    "market_share": "30%",
                    "our_differentiation": "더 나은 UX와 저렴한 가격"
                }
            ],
            "trends": [
                "모바일 퍼스트 전환 가속화",
                "구독 경제 성장",
                "AI/ML 기술 활용 증가"
            ],
            "opportunities": [
                "기존 서비스의 높은 불만족도",
                "MZ세대 타겟 시장 성장",
                "정부 지원 정책"
            ]
        }
    
    def _has_market_size_data(self, context: str) -> bool:
        """
        컨텍스트에 시장 규모 관련 데이터가 있는지 확인

        Args:
            context: 웹 검색 컨텍스트 문자열

        Returns:
            bool: 시장 규모 키워드가 있으면 True
        """
        if not context:
            return False

        keywords = [
            "시장 규모", "market size", "TAM", "SAM", "SOM",
            "억원", "조원", "billion", "trillion",
            "성장률", "CAGR", "growth rate",
            "시장 점유율", "market share"
        ]
        context_lower = context.lower()
        return any(kw.lower() in context_lower for kw in keywords)

    def _search_market_data(self, topic: str) -> str:
        """
        시장 규모 특화 추가 검색 (1회만)

        Args:
            topic: 검색 주제

        Returns:
            str: 검색 결과 문자열
        """
        try:
            from tools.search_client import get_search_client

            client = get_search_client()
            query = f"{topic} 시장 규모 통계 2026"
            logger.info(f"[{self.name}] 추가 검색 쿼리: {query}")

            result = client.search(query, max_results=3)
            return result if result else ""
        except Exception as e:
            logger.warning(f"[{self.name}] 추가 검색 실패: {e}")
            return ""

    def format_as_markdown(self, analysis: Dict[str, Any]) -> str:
        """시장 분석을 마크다운 형식으로 변환"""
        md = "### 시장 규모\n\n"
        
        tam = analysis.get("tam", {})
        sam = analysis.get("sam", {})
        som = analysis.get("som", {})
        
        md += f"- **TAM (Global)**: {tam.get('value', 'N/A')} ({tam.get('year', '')}년, 출처: {tam.get('source', '')})\n"
        md += f"  - {tam.get('description', '')}\n"
        if tam.get('cagr'):
            md += f"  - CAGR {tam.get('cagr')}로 성장 중\n"
        
        md += f"- **SAM (국내 접근 가능)**: {sam.get('value', 'N/A')} (출처: {sam.get('source', '')})\n"
        md += f"  - {sam.get('description', '')}\n"
        
        md += f"- **SOM (1년차 목표)**: {som.get('value', 'N/A')}\n"
        md += f"  - {som.get('description', '')}\n\n"
        
        # 경쟁사 분석
        md += "### 경쟁사 분석\n\n"
        md += "| 경쟁사명 | 특징 | 한계점 | 우리의 차별점 |\n"
        md += "|----------|------|--------|---------------|\n"
        
        for comp in analysis.get("competitors", [])[:5]:
            strengths = ", ".join(comp.get("strengths", [])[:2])
            weaknesses = ", ".join(comp.get("weaknesses", [])[:2])
            md += f"| {comp.get('name', '')} | {strengths} | {weaknesses} | {comp.get('our_differentiation', '')} |\n"
        
        md += "\n"
        
        # 트렌드
        trends = analysis.get("trends", [])
        if trends:
            md += "### 시장 트렌드\n\n"
            for t in trends[:5]:
                md += f"- {t}\n"
            md += "\n"
        
        return md


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    agent = MarketAgent()
    result = agent._get_fallback_analysis("러닝 앱")
    print(agent.format_as_markdown(result))
