"""
PlanCraft - Risk Analysis Agent (리스크 분석 에이전트)

기획서의 리스크 섹션을 전문적으로 생성합니다.
- 8가지 리스크 카테고리 분석
- 발생확률 × 영향도 정량화
- 구체적 대응 Action Items
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field
from utils.llm import get_llm
from utils.file_logger import get_file_logger

logger = get_file_logger()


# =============================================================================
# 출력 스키마 정의
# =============================================================================

class Risk(BaseModel):
    """리스크 항목"""
    category: str = Field(description="카테고리 (기술/비즈니스/운영/규제/경쟁/재무/인력/외부)")
    title: str = Field(description="리스크 제목")
    description: str = Field(description="상세 설명")
    probability: str = Field(description="발생 확률 (높음/중간/낮음)")
    impact: str = Field(description="영향도 (높음/중간/낮음)")
    risk_score: int = Field(description="위험 점수 (1-9)")
    mitigation: str = Field(description="대응 전략")
    owner: str = Field(default="미정", description="담당자/팀")
    kri: str = Field(default="", description="핵심 위험 지표 (KRI)")


class RiskAnalysis(BaseModel):
    """리스크 분석 전체"""
    risks: List[Risk] = Field(description="리스크 목록 (최소 5개)")
    top_risks: List[str] = Field(description="상위 3개 핵심 리스크")
    overall_risk_level: str = Field(description="전체 리스크 수준 (높음/중간/낮음)")
    contingency_plan: str = Field(description="비상 계획")


# =============================================================================
# Risk Agent 클래스
# =============================================================================

class RiskAgent:
    """
    리스크 분석 전문 에이전트
    
    기획서의 리스크를 체계적으로 분석합니다.
    """
    
    RISK_CATEGORIES = [
        "기술",      # 개발 난이도, 기술 부채
        "비즈니스",  # BM 실패, 시장 반응
        "운영",      # 인프라, 고객 지원
        "규제",      # 법률, 개인정보
        "경쟁",      # 시장 경쟁, 대기업 진입
        "재무",      # 자금 조달, 현금 흐름
        "인력",      # 핵심 인력, 채용
        "외부",      # 경제 상황, 천재지변
    ]
    
    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.4)
        self.name = "RiskAgent"
    
    def run(
        self,
        service_overview: str,
        business_model: Dict[str, Any],
        tech_stack: str = None
    ) -> Dict[str, Any]:
        """
        리스크 분석을 수행합니다.
        
        Args:
            service_overview: 서비스 개요
            business_model: BM Agent 출력
            tech_stack: 기술 스택
            
        Returns:
            RiskAnalysis dict
        """
        from prompts.specialist_prompts.risk_prompt import (
            RISK_SYSTEM_PROMPT,
            RISK_USER_PROMPT
        )
        
        logger.info(f"[{self.name}] 리스크 분석 시작")
        
        user_prompt = RISK_USER_PROMPT.format(
            service_overview=service_overview,
            business_model=str(business_model),
            tech_stack=tech_stack or "(기술 스택 미정)"
        )
        
        messages = [
            {"role": "system", "content": RISK_SYSTEM_PROMPT},
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
            
            logger.info(f"[{self.name}] 리스크 분석 완료")
            logger.debug(f"  - 리스크 수: {len(result.get('risks', []))}")
            logger.debug(f"  - 전체 위험 수준: {result.get('overall_risk_level', 'N/A')}")
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 리스크 분석 실패: {e}")
            return self._get_fallback_analysis(service_overview)
    
    def _get_fallback_analysis(self, service_overview: str) -> Dict[str, Any]:
        """Fallback 리스크 분석"""
        return {
            "risks": [
                {
                    "category": "기술",
                    "title": "위치 기반 서비스 정확도 문제",
                    "description": "GPS 정확도가 낮은 환경에서 서비스 품질 저하 가능",
                    "probability": "중간",
                    "impact": "높음",
                    "risk_score": 6,
                    "mitigation": "Wi-Fi/셀룰러 보조 위치 확인, 오프라인 모드 지원",
                    "owner": "개발팀",
                    "kri": "위치 오차율 10m 이하 유지"
                },
                {
                    "category": "비즈니스",
                    "title": "초기 사용자 확보 실패",
                    "description": "네트워크 효과 발생 전 사용자 이탈 가능",
                    "probability": "중간",
                    "impact": "높음",
                    "risk_score": 6,
                    "mitigation": "론칭 지역 집중 전략, 인플루언서 마케팅",
                    "owner": "마케팅팀",
                    "kri": "월 신규 가입자 1,000명 이상"
                },
                {
                    "category": "규제",
                    "title": "개인정보 보호 규정 준수",
                    "description": "위치 정보 활용에 따른 개인정보보호법 리스크",
                    "probability": "낮음",
                    "impact": "높음",
                    "risk_score": 4,
                    "mitigation": "GDPR/개인정보보호법 준수, 데이터 암호화",
                    "owner": "법무팀",
                    "kri": "개인정보 관련 민원 0건"
                },
                {
                    "category": "경쟁",
                    "title": "대기업 시장 진입",
                    "description": "Strava, Nike 등 기존 강자의 유사 기능 추가",
                    "probability": "높음",
                    "impact": "중간",
                    "risk_score": 6,
                    "mitigation": "차별화된 소셜 기능에 집중, 니치 시장 공략",
                    "owner": "전략팀",
                    "kri": "유료 전환율 5% 이상 유지"
                },
                {
                    "category": "재무",
                    "title": "자금 조달 실패",
                    "description": "시리즈 A 투자 유치 실패 시 운영 자금 부족",
                    "probability": "중간",
                    "impact": "높음",
                    "risk_score": 6,
                    "mitigation": "12개월 런웨이 확보, 수익성 조기 달성 목표",
                    "owner": "대표",
                    "kri": "월 소진액 대비 잔고 6개월 이상"
                }
            ],
            "top_risks": [
                "초기 사용자 확보 실패",
                "대기업 시장 진입",
                "자금 조달 실패"
            ],
            "overall_risk_level": "중간",
            "contingency_plan": "핵심 리스크 발생 시 MVP 범위 축소, 피봇 검토"
        }
    
    def format_as_markdown(self, analysis: Dict[str, Any]) -> str:
        """리스크 분석을 마크다운 형식으로 변환"""
        md = "### 리스크 및 대응 방안\n\n"
        
        md += "| 리스크 구분 | 리스크 내용 | 영향 | 확률 | 대응 방안 |\n"
        md += "|-------------|-------------|------|------|----------|\n"
        
        for risk in analysis.get("risks", [])[:8]:
            md += f"| {risk.get('category', '')} | {risk.get('title', '')} | {risk.get('impact', '')} | {risk.get('probability', '')} | {risk.get('mitigation', '')} |\n"
        
        md += "\n"
        
        # 상위 리스크
        top = analysis.get("top_risks", [])
        if top:
            md += "**핵심 리스크 TOP 3:**\n"
            for i, r in enumerate(top[:3], 1):
                md += f"{i}. {r}\n"
            md += "\n"
        
        # 비상 계획
        contingency = analysis.get("contingency_plan", "")
        if contingency:
            md += f"**비상 계획:** {contingency}\n\n"
        
        return md


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    agent = RiskAgent()
    result = agent._get_fallback_analysis("러닝 앱")
    print(agent.format_as_markdown(result))
