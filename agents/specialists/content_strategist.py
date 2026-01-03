"""
PlanCraft - Content Strategist Agent (콘텐츠 전략 에이전트)

기획서의 마케팅/브랜딩 섹션을 전문적으로 생성합니다.
- 브랜드 컨셉 및 슬로건
- 콘텐츠 채널 전략
- 초기 사용자 유입 전략

출력 형식:
    {
        "brand_concept": {...},
        "core_message": "...",
        "content_channels": [...],
        "acquisition_strategy": "..."
    }
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.file_logger import FileLogger
import json

logger = FileLogger()


# =============================================================================
# 출력 스키마 정의
# =============================================================================

class BrandConcept(BaseModel):
    """브랜드 컨셉"""
    persona: str = Field(description="서비스 페르소나 (의인화)")
    slogan: str = Field(description="핵심 슬로건")
    tone_and_manner: str = Field(description="톤앤매너")


class ContentChannel(BaseModel):
    """콘텐츠 채널"""
    channel: str = Field(description="채널명 (Instagram, YouTube 등)")
    purpose: str = Field(description="활용 목적")
    content_type: str = Field(description="콘텐츠 유형")
    frequency: str = Field(description="게시 빈도")


class ContentStrategy(BaseModel):
    """콘텐츠 전략 분석 전체"""
    brand_concept: BrandConcept = Field(description="브랜드 컨셉")
    core_message: str = Field(description="핵심 메시지 (One Liner)")
    content_channels: List[ContentChannel] = Field(description="채널 전략")
    acquisition_strategy: str = Field(description="초기 사용자 유입 전략")
    viral_hooks: Optional[List[str]] = Field(default=None, description="바이럴 포인트")


# =============================================================================
# Content Strategist Agent 클래스
# =============================================================================

CONTENT_SYSTEM_PROMPT = """당신은 **Content & Brand Strategist (CMO급)**입니다.

## 역할
서비스의 성공을 위한 **브랜딩, 콘텐츠 전략, 사용자 유입(AARRR) 전략**을 수립합니다.
기술적 기능보다는 '사용자가 왜 이 서비스를 써야 하는가(Why)'에 집중합니다.

## 분석 포인트
1. **Brand Concept**: 서비스의 페르소나, 톤앤매너, 슬로건
2. **Core Message**: 타겟 사용자에게 전달할 단 하나의 핵심 메시지
3. **Content Strategy**: 블로그, SNS, 커뮤니티 등 채널별 콘텐츠 운영 방안
4. **User Acquisition**: 초기 사용자 1,000명 확보를 위한 게릴라 마케팅 전략
5. **Viral Hooks**: 자연스러운 바이럴을 유도할 수 있는 요소

## 출력 형식 (JSON)
{
    "brand_concept": {
        "persona": "친근하고 든든한 러닝 코치",
        "slogan": "혼자 달려도 함께 뛰는 느낌",
        "tone_and_manner": "친근하고 유쾌하며 응원하는 톤"
    },
    "core_message": "운동이 재미있어지는 순간",
    "content_channels": [
        {
            "channel": "Instagram",
            "purpose": "인증샷 공유 및 커뮤니티 형성",
            "content_type": "사용자 UGC, 도전 과제",
            "frequency": "주 3-5회"
        }
    ],
    "acquisition_strategy": "지역 러닝 크루와 제휴...",
    "viral_hooks": ["친구 초대 시 보상", "업적 공유 기능"]
}
"""


class ContentStrategistAgent:
    """
    콘텐츠/브랜딩 전문 에이전트

    마케팅 전략 및 브랜드 아이덴티티를 수립합니다.
    """

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.7)  # 마케팅은 창의적이어야 함
        self.name = "ContentStrategistAgent"

    def run(
        self,
        service_overview: str,
        target_users: str = "",
        market_analysis: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        콘텐츠/브랜딩 전략을 수립합니다.

        Args:
            service_overview: 서비스 개요
            target_users: 타겟 사용자
            market_analysis: Market Agent 출력 (타겟 정보)

        Returns:
            ContentStrategy dict
        """
        logger.info(f"[{self.name}] 콘텐츠 전략 수립 시작")

        market_context = ""
        if market_analysis:
            market_context = json.dumps(market_analysis, ensure_ascii=False)[:500]

        user_prompt = f"""
## 서비스 개요
{service_overview}

## 타겟 사용자
{target_users or "(미지정)"}

## 시장 배경
{market_context or "(시장 분석 데이터 없음)"}

위 내용을 바탕으로 매력적인 콘텐츠 및 브랜딩 전략을 수립해주세요.
반드시 JSON 형식으로 출력하세요.
"""

        messages = [
            {"role": "system", "content": CONTENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.llm.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)

            # JSON 파싱
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

            result = json.loads(json_str)

            logger.info(f"[{self.name}] 콘텐츠 전략 수립 완료")
            brand = result.get("brand_concept", {})
            logger.debug(f"  - Slogan: {brand.get('slogan', 'N/A')}")
            logger.debug(f"  - Core Message: {result.get('core_message', 'N/A')}")

            return result

        except Exception as e:
            logger.error(f"[{self.name}] 콘텐츠 전략 수립 실패: {e}")
            return self._get_fallback_strategy(service_overview)

    def _get_fallback_strategy(self, service_overview: str) -> Dict[str, Any]:
        """Fallback 콘텐츠 전략"""
        return {
            "brand_concept": {
                "persona": "친절하고 전문적인 파트너",
                "slogan": "더 쉽게, 더 빠르게",
                "tone_and_manner": "친근하면서도 신뢰감 있는 톤"
            },
            "core_message": "복잡한 일상을 간편하게",
            "content_channels": [
                {
                    "channel": "Instagram",
                    "purpose": "브랜드 인지도 및 커뮤니티 형성",
                    "content_type": "사용 팁, 사용자 후기, 이벤트",
                    "frequency": "주 3회"
                },
                {
                    "channel": "YouTube",
                    "purpose": "튜토리얼 및 가치 전달",
                    "content_type": "사용 가이드, 비하인드 스토리",
                    "frequency": "주 1회"
                },
                {
                    "channel": "블로그/SEO",
                    "purpose": "검색 유입",
                    "content_type": "How-to 가이드, 업계 트렌드",
                    "frequency": "주 2회"
                }
            ],
            "acquisition_strategy": "1. 초기 1,000명: 타겟 커뮤니티 집중 마케팅 + 인플루언서 시딩\n2. 얼리어답터 리워드 프로그램\n3. 바이럴 루프 설계 (친구 초대 보상)",
            "viral_hooks": [
                "친구 초대 시 양쪽 모두 혜택",
                "업적/결과 SNS 공유 기능",
                "밈화 가능한 UI 요소"
            ]
        }

    def format_as_markdown(self, strategy: Dict[str, Any]) -> str:
        """콘텐츠 전략을 마크다운 형식으로 변환"""
        md = "### 브랜드 컨셉\n\n"

        brand = strategy.get("brand_concept", {})
        md += f"- **페르소나**: {brand.get('persona', 'N/A')}\n"
        md += f"- **슬로건**: \"{brand.get('slogan', 'N/A')}\"\n"
        md += f"- **톤앤매너**: {brand.get('tone_and_manner', 'N/A')}\n\n"

        # 핵심 메시지
        core_msg = strategy.get("core_message", "")
        if core_msg:
            md += f"**핵심 메시지**: \"{core_msg}\"\n\n"

        # 채널 전략
        channels = strategy.get("content_channels", [])
        if channels:
            md += "### 콘텐츠 채널 전략\n\n"
            md += "| 채널 | 목적 | 콘텐츠 유형 | 빈도 |\n"
            md += "|------|------|------------|------|\n"

            for ch in channels[:5]:
                if isinstance(ch, dict):
                    md += f"| {ch.get('channel', '')} | {ch.get('purpose', '')} | {ch.get('content_type', '')} | {ch.get('frequency', '')} |\n"
                else:
                    md += f"| {ch} | - | - | - |\n"
            md += "\n"

        # 사용자 유입 전략
        acquisition = strategy.get("acquisition_strategy", "")
        if acquisition:
            md += "### 초기 사용자 유입 전략\n\n"
            md += f"{acquisition}\n\n"

        # 바이럴 포인트
        viral = strategy.get("viral_hooks", [])
        if viral:
            md += "### 바이럴 포인트\n\n"
            for v in viral[:5]:
                md += f"- {v}\n"
            md += "\n"

        return md


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    agent = ContentStrategistAgent()
    result = agent._get_fallback_strategy("러닝 앱")
    print(agent.format_as_markdown(result))
