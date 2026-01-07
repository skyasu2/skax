"""
PlanCraft - Financial Agent (재무 시뮬레이션 에이전트)

기획서의 재무 계획 섹션을 전문적으로 생성합니다.
- 초기 투자 비용 상세 분해
- 월별 매출/비용 시뮬레이션
- BEP(손익분기점) 계산
- 낙관/기본/보수 3시나리오

출력 형식:
    {
        "initial_investment": {...},
        "monthly_projection": {...},
        "bep_analysis": {...},
        "scenarios": {...}
    }
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from utils.llm import get_llm
from utils.file_logger import get_file_logger

logger = get_file_logger()


# =============================================================================
# 출력 스키마 정의
# =============================================================================

class InvestmentItem(BaseModel):
    """투자 항목"""
    category: str = Field(description="항목 카테고리 (개발비/마케팅/운영/기타)")
    item: str = Field(description="세부 항목명")
    amount: int = Field(description="금액 (원)")
    note: str = Field(default="", description="비고")


class MonthlyProjection(BaseModel):
    """월별 손익 예측"""
    period: str = Field(description="기간 (예: 1-3개월)")
    revenue: int = Field(description="매출 (원)")
    cost: int = Field(description="비용 (원)")
    profit: int = Field(description="영업이익 (원)")
    revenue_formula: str = Field(description="매출 산출 근거 (예: MAU × 전환율 × 객단가)")


class BEPAnalysis(BaseModel):
    """손익분기점 분석"""
    bep_month: int = Field(description="BEP 달성 예상 월차")
    monthly_fixed_cost: int = Field(description="월 고정비")
    unit_price: int = Field(description="객단가")
    required_customers: int = Field(description="필요 고객 수")
    formula: str = Field(description="BEP 산출 공식")


class FinancialPlan(BaseModel):
    """재무 계획 전체"""
    initial_investment: list[InvestmentItem] = Field(description="초기 투자 항목")
    total_investment: int = Field(description="총 초기 투자금")
    monthly_projections: list[MonthlyProjection] = Field(description="월별 손익")
    annual_revenue: int = Field(description="1년차 연간 매출")
    annual_profit: int = Field(description="1년차 연간 영업이익")
    bep: BEPAnalysis = Field(description="BEP 분석")
    som_gap_explanation: str = Field(description="SOM vs 1년차 Gap 설명")


# =============================================================================
# Financial Agent 클래스
# =============================================================================

class FinancialAgent:
    """
    재무 시뮬레이션 전문 에이전트
    
    기획서의 재무 계획을 전문적으로 생성합니다.
    """
    
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.3)  # 수치 계산이므로 낮은 temperature
        self.name = "FinancialAgent"
    
    def run(
        self,
        service_overview: str,
        business_model: Dict[str, Any],
        market_analysis: Dict[str, Any],
        development_scope: str = "MVP 3개월",
        analysis_depth: str = "standard",  # [FIX] 추가된 인자
        financial_requirements: str = ""   # [FIX] 심층 분석용 추가 요구사항
    ) -> Dict[str, Any]:
        """
        재무 계획을 생성합니다.
        
        Args:
            service_overview: 서비스 개요
            business_model: BM Agent 출력 (수익 모델, 가격 전략)
            market_analysis: Market Agent 출력 (TAM/SAM/SOM)
            development_scope: 개발 범위 (MVP 3개월 등)
            analysis_depth: 분석 깊이 ("standard" 또는 "deep")
            financial_requirements: 심층 분석 시 추가 요구사항
            
        Returns:
            FinancialPlan dict
        """
        from prompts.specialist_prompts.financial_prompt import (
            FINANCIAL_SYSTEM_PROMPT,
            FINANCIAL_USER_PROMPT
        )
        
        logger.info(f"[{self.name}] 재무 계획 생성 시작")
        
        # 프롬프트 구성
        user_prompt = FINANCIAL_USER_PROMPT.format(
            service_overview=service_overview,
            business_model=str(business_model),
            market_analysis=str(market_analysis),
            development_scope=development_scope
        )
        
        messages = [
            {"role": "system", "content": FINANCIAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # LLM 호출
            response = self.llm.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # JSON 파싱
            import json
            import re
            
            # JSON 블록 추출
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSON 블록이 없으면 전체 내용 시도
                json_str = content
            
            result = json.loads(json_str)
            
            logger.info(f"[{self.name}] 재무 계획 생성 완료")
            logger.debug(f"  - 총 투자금: {result.get('total_investment', 'N/A')}")
            logger.debug(f"  - 연간 매출: {result.get('annual_revenue', 'N/A')}")
            logger.debug(f"  - BEP: {result.get('bep', {}).get('bep_month', 'N/A')}개월")
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 재무 계획 생성 실패: {e}")
            return self._get_fallback_plan(service_overview)
    
    def _get_fallback_plan(self, service_overview: str) -> Dict[str, Any]:
        """Fallback 재무 계획 (LLM 실패 시)"""
        return {
            "initial_investment": [
                {"category": "개발비", "item": "앱 개발 및 테스트", "amount": 100000000, "note": "3개월 MVP"},
                {"category": "서버비", "item": "AWS 인프라 구축", "amount": 30000000, "note": "1년 선납"},
                {"category": "마케팅", "item": "초기 사용자 유치", "amount": 50000000, "note": "론칭 캠페인"},
                {"category": "운영비", "item": "인건비 (3개월)", "amount": 60000000, "note": "3명 기준"},
            ],
            "total_investment": 240000000,
            "monthly_projections": [
                {"period": "1-3개월", "revenue": 10000000, "cost": 60000000, "profit": -50000000, "revenue_formula": "MAU 1,000 × 전환율 10% × 객단가 100,000원"},
                {"period": "4-6개월", "revenue": 50000000, "cost": 40000000, "profit": 10000000, "revenue_formula": "MAU 5,000 × 전환율 10% × 객단가 100,000원"},
                {"period": "7-12개월", "revenue": 150000000, "cost": 60000000, "profit": 90000000, "revenue_formula": "MAU 15,000 × 전환율 10% × 객단가 100,000원"},
            ],
            "annual_revenue": 210000000,
            "annual_profit": 50000000,
            "bep": {
                "bep_month": 12,
                "monthly_fixed_cost": 15000000,
                "unit_price": 10000,
                "required_customers": 1500,
                "formula": "월 고정비 1,500만원 / 객단가 10,000원 = 월 1,500명 필요"
            },
            "som_gap_explanation": "SOM 목표 대비 1년차 달성률 약 10%. 2년차 마케팅 확대로 30%, 3년차 B2B 진출로 50% 목표."
        }
    
    def format_as_markdown(self, plan: Dict[str, Any]) -> str:
        """재무 계획을 마크다운 형식으로 변환"""
        md = "### 초기 투자 계획\n\n"
        md += "| 항목 | 금액 | 세부 내역 |\n"
        md += "|------|------|----------|\n"
        
        for item in plan.get("initial_investment", []):
            amount_str = f"{item['amount']:,}원"
            md += f"| {item['category']} - {item['item']} | {amount_str} | {item.get('note', '')} |\n"
        
        total = plan.get("total_investment", 0)
        md += f"| **합계** | **{total:,}원** | - |\n\n"
        
        md += "### 예상 매출 및 손익 (1년차)\n\n"
        md += "| 구분 | 1-3개월 | 4-6개월 | 7-12개월 | 연간 합계 |\n"
        md += "|------|---------|---------|----------|----------|\n"
        
        projections = plan.get("monthly_projections", [])
        if len(projections) >= 3:
            rev_row = "| 매출 |"
            cost_row = "| 비용 |"
            profit_row = "| **영업이익** |"
            
            for p in projections:
                rev_row += f" {p['revenue']:,}원 |"
                cost_row += f" {p['cost']:,}원 |"
                profit_row += f" **{p['profit']:,}원** |"
            
            annual_rev = plan.get("annual_revenue", 0)
            annual_cost = sum(p['cost'] for p in projections)
            annual_profit = plan.get("annual_profit", 0)
            
            rev_row += f" {annual_rev:,}원 |"
            cost_row += f" {annual_cost:,}원 |"
            profit_row += f" **{annual_profit:,}원** |"
            
            md += rev_row + "\n"
            md += cost_row + "\n"
            md += profit_row + "\n\n"
        
        # BEP
        bep = plan.get("bep", {})
        md += "### 손익분기점 (BEP)\n\n"
        md += f"- **예상 BEP 시점**: 서비스 출시 후 {bep.get('bep_month', 12)}개월\n"
        md += f"- **BEP 달성 조건**: 유료 사용자 {bep.get('required_customers', 0):,}명 또는 월 매출 {bep.get('monthly_fixed_cost', 0):,}원 달성 시\n"
        md += f"- **산출 근거**: {bep.get('formula', '')}\n\n"
        
        # SOM Gap
        md += "### SOM vs 1년차 매출 Gap\n\n"
        md += plan.get("som_gap_explanation", "") + "\n"
        
        return md


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    agent = FinancialAgent()
    
    # 테스트 데이터
    result = agent._get_fallback_plan("러닝 앱")
    print(agent.format_as_markdown(result))
