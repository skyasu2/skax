"""
PlanCraft - Business Model Agent (비즈니스 모델 에이전트)

기획서의 비즈니스 모델 섹션을 전문적으로 생성합니다.
- 수익 모델 다각화 (5개 이상 후보)
- 가격 전략 (경쟁사 벤치마킹 기반)
- B2B/B2C 계층 구조
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field
from utils.llm import get_llm
from utils.file_logger import get_file_logger

logger = get_file_logger()


# =============================================================================
# 출력 스키마 정의
# =============================================================================

class RevenueModel(BaseModel):
    """수익 모델"""
    name: str = Field(description="수익 모델명")
    type: str = Field(description="유형 (B2C/B2B/B2B2C)")
    description: str = Field(description="설명")
    expected_ratio: int = Field(description="예상 매출 비중 (%)")
    pricing: str = Field(description="가격 정책")
    competitors_benchmark: str = Field(description="경쟁사 벤치마킹")


class PricingTier(BaseModel):
    """가격 계층"""
    tier_name: str = Field(description="플랜명 (Free/Basic/Pro/Enterprise)")
    price: str = Field(description="가격 (월/연)")
    features: List[str] = Field(description="포함 기능")
    target: str = Field(description="타겟 사용자")


class BusinessModelAnalysis(BaseModel):
    """비즈니스 모델 분석 전체"""
    primary_model: RevenueModel = Field(description="메인 수익 모델")
    secondary_models: List[RevenueModel] = Field(description="보조 수익 모델들")
    pricing_tiers: List[PricingTier] = Field(description="가격 계층")
    revenue_mix: Dict[str, int] = Field(description="수익 믹스 (1년차/3년차)")
    moat: str = Field(description="해자 (경쟁 우위)")


# =============================================================================
# BM Agent 클래스
# =============================================================================

class BMAgent:
    """
    비즈니스 모델 전문 에이전트
    
    수익 모델 다각화 및 가격 전략을 수립합니다.
    """
    
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.5)
        self.name = "BMAgent"
    
    def run(
        self,
        service_overview: str,
        target_users: str,
        competitors: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        비즈니스 모델을 분석합니다.
        
        Args:
            service_overview: 서비스 개요
            target_users: 타겟 사용자
            competitors: 경쟁사 정보 (Market Agent 출력)
            
        Returns:
            BusinessModelAnalysis dict
        """
        from prompts.specialist_prompts.bm_prompt import (
            BM_SYSTEM_PROMPT,
            BM_USER_PROMPT
        )
        
        logger.info(f"[{self.name}] 비즈니스 모델 분석 시작")
        
        competitors_str = ""
        if competitors:
            for c in competitors[:5]:
                competitors_str += f"- {c.get('name', '')}: {c.get('description', '')}\n"
        
        user_prompt = BM_USER_PROMPT.format(
            service_overview=service_overview,
            target_users=target_users,
            competitors_info=competitors_str or "(경쟁사 정보 없음)"
        )
        
        messages = [
            {"role": "system", "content": BM_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            response = self.llm.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)
            
            import json
            import re
            
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            result = json.loads(json_str)
            
            logger.info(f"[{self.name}] 비즈니스 모델 분석 완료")
            logger.debug(f"  - 메인 모델: {result.get('primary_model', {}).get('name', 'N/A')}")
            logger.debug(f"  - 가격 계층: {len(result.get('pricing_tiers', []))}개")
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 비즈니스 모델 분석 실패: {e}")
            return self._get_fallback_bm(service_overview)
    
    def _get_fallback_bm(self, service_overview: str) -> Dict[str, Any]:
        """Fallback 비즈니스 모델"""
        return {
            "primary_model": {
                "name": "프리미엄 구독",
                "type": "B2C",
                "description": "월정액 프리미엄 기능 제공",
                "expected_ratio": 60,
                "pricing": "월 9,900원 / 연 99,000원 (2개월 무료)",
                "competitors_benchmark": "경쟁사 평균 $9.99/월 대비 10% 저렴"
            },
            "secondary_models": [
                {
                    "name": "기업 라이선스",
                    "type": "B2B",
                    "description": "기업 복지/웰니스 프로그램 제휴",
                    "expected_ratio": 25,
                    "pricing": "직원당 월 5,000원 (최소 50명)",
                    "competitors_benchmark": "B2B 진출로 차별화"
                },
                {
                    "name": "인앱 광고",
                    "type": "B2C",
                    "description": "무료 사용자 대상 비침입적 광고",
                    "expected_ratio": 10,
                    "pricing": "CPM $2-5",
                    "competitors_benchmark": "광고 의존도 최소화"
                },
                {
                    "name": "제휴 수수료",
                    "type": "B2B2C",
                    "description": "관련 상품/서비스 추천 수수료",
                    "expected_ratio": 5,
                    "pricing": "거래액의 5-10%",
                    "competitors_benchmark": "추가 수익원 확보"
                }
            ],
            "pricing_tiers": [
                {
                    "tier_name": "Free",
                    "price": "무료",
                    "features": ["기본 기능", "광고 포함"],
                    "target": "라이트 유저, 신규 사용자"
                },
                {
                    "tier_name": "Premium",
                    "price": "월 9,900원",
                    "features": ["모든 기능", "광고 제거", "고급 분석"],
                    "target": "헤비 유저, 진성 사용자"
                },
                {
                    "tier_name": "Enterprise",
                    "price": "별도 협의",
                    "features": ["팀 관리", "API 액세스", "전담 지원"],
                    "target": "기업 고객"
                }
            ],
            "revenue_mix": {
                "year1": {"subscription": 60, "b2b": 10, "ads": 25, "affiliate": 5},
                "year3": {"subscription": 50, "b2b": 35, "ads": 10, "affiliate": 5}
            },
            "moat": "위치 기반 소셜 기능 + 커뮤니티 네트워크 효과"
        }
    
    def format_as_markdown(self, bm: Dict[str, Any]) -> str:
        """비즈니스 모델을 마크다운 형식으로 변환"""
        md = "### 수익 모델\n\n"
        
        primary = bm.get("primary_model", {})
        md += f"1. **{primary.get('name', '')}** ({primary.get('type', '')}): {primary.get('description', '')}\n"
        md += f"   - 가격: {primary.get('pricing', '')}\n"
        md += f"   - 예상 매출 비중: {primary.get('expected_ratio', 0)}%\n\n"
        
        for i, model in enumerate(bm.get("secondary_models", []), start=2):
            md += f"{i}. **{model.get('name', '')}** ({model.get('type', '')}): {model.get('description', '')}\n"
            md += f"   - 가격: {model.get('pricing', '')}\n"
            md += f"   - 예상 매출 비중: {model.get('expected_ratio', 0)}%\n\n"
        
        # 가격 계층
        md += "### 가격 정책\n\n"
        md += "| 플랜 | 가격 | 포함 기능 | 타겟 |\n"
        md += "|------|------|----------|------|\n"
        
        for tier in bm.get("pricing_tiers", []):
            features = ", ".join(tier.get("features", [])[:3])
            md += f"| {tier.get('tier_name', '')} | {tier.get('price', '')} | {features} | {tier.get('target', '')} |\n"
        
        md += "\n"
        
        # 해자
        moat = bm.get("moat", "")
        if moat:
            md += f"### 경쟁 우위 (Moat)\n\n{moat}\n\n"
        
        return md


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    agent = BMAgent()
    result = agent._get_fallback_bm("러닝 앱")
    print(agent.format_as_markdown(result))
