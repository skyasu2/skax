"""
PlanCraft - Tech Architect Agent (기술 아키텍처 에이전트)

기획서의 기술 스택 및 아키텍처 섹션을 전문적으로 생성합니다.
- 기술 스택 추천 (Frontend/Backend/DB/Infra)
- 시스템 아키텍처 설계
- 개발 로드맵 수립

출력 형식:
    {
        "recommended_stack": {...},
        "architecture_desc": "...",
        "technical_challenges": [...],
        "roadmap": {...}
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

class TechStack(BaseModel):
    """기술 스택"""
    frontend: str = Field(description="프론트엔드 (예: React, Next.js)")
    backend: str = Field(description="백엔드 (예: Node.js, FastAPI)")
    database: str = Field(description="데이터베이스 (예: PostgreSQL, MongoDB)")
    infrastructure: str = Field(description="인프라 (예: AWS, GCP)")
    reasoning: Optional[str] = Field(default=None, description="기술 선택 이유")


class DevelopmentRoadmap(BaseModel):
    """개발 로드맵"""
    phase1_mvp: str = Field(description="Phase 1 - MVP (기간 및 범위)")
    phase2_scale: str = Field(description="Phase 2 - 확장 (기간 및 범위)")
    phase3_optimize: Optional[str] = Field(default=None, description="Phase 3 - 최적화")


class TechArchitecture(BaseModel):
    """기술 아키텍처 분석 전체"""
    recommended_stack: TechStack = Field(description="추천 기술 스택")
    architecture_desc: str = Field(description="시스템 아키텍처 설명")
    technical_challenges: List[str] = Field(description="예상 기술적 난관")
    roadmap: DevelopmentRoadmap = Field(description="개발 로드맵")


# =============================================================================
# Tech Architect Agent 클래스
# =============================================================================

TECH_SYSTEM_PROMPT = """당신은 15년 경력의 **Technical Architect (CTO급)**입니다.

## 역할
제시된 서비스 기획안을 바탕으로 최적의 **기술 아키텍처와 개발 로드맵**을 설계합니다.
비즈니스 요구사항을 실현 가능한 기술 스택으로 변환하는 것이 목표입니다.

## 분석 포인트
1. **Tech Stack Recommendation**: 프론트엔드, 백엔드, DB, 인프라 등 (이유 포함)
2. **System Architecture**: 클라우드 구조, MSA vs Monolith 등
3. **Key Technical Challenges**: 예상되는 기술적 난관 및 해결 방안 (예: 실시간성, 대용량 처리)
4. **Development Roadmap**: MVP 단계별 개발 범위 및 추정 기간

## 출력 형식 (JSON)
{
    "recommended_stack": {
        "frontend": "React.js with TypeScript",
        "backend": "Node.js with NestJS",
        "database": "PostgreSQL",
        "infrastructure": "AWS (ECS, RDS, S3)",
        "reasoning": "기술 선택 이유 설명"
    },
    "architecture_desc": "시스템 아키텍처 상세 설명...",
    "technical_challenges": ["도전 과제 1", "도전 과제 2"],
    "roadmap": {
        "phase1_mvp": "Phase 1 (3개월): MVP 핵심 기능...",
        "phase2_scale": "Phase 2 (3개월): 확장 기능...",
        "phase3_optimize": "Phase 3 (3개월): 최적화..."
    }
}
"""


class TechArchitectAgent:
    """
    기술 아키텍처 전문 에이전트

    기술 스택 선정 및 시스템 아키텍처를 설계합니다.
    """

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.3)  # 기술 설계는 명확해야 함
        self.name = "TechArchitectAgent"

    def run(
        self,
        service_overview: str,
        target_users: str = "",
        user_constraints: List[str] = None
    ) -> Dict[str, Any]:
        """
        기술 아키텍처를 설계합니다.

        Args:
            service_overview: 서비스 개요
            target_users: 타겟 사용자
            user_constraints: 사용자 제약사항 (기술 스택 지정 등)

        Returns:
            TechArchitecture dict
        """
        logger.info(f"[{self.name}] 기술 아키텍처 설계 시작")

        constraints_str = ""
        if user_constraints:
            constraints_str = "\n".join([f"- {c}" for c in user_constraints])

        user_prompt = f"""
## 서비스 개요
{service_overview}

## 타겟 사용자
{target_users or "(미지정)"}

## 제약 사항
{constraints_str or "(없음)"}

위 내용을 바탕으로 기술 아키텍처를 설계해주세요.
반드시 JSON 형식으로 출력하세요.
"""

        messages = [
            {"role": "system", "content": TECH_SYSTEM_PROMPT},
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

            logger.info(f"[{self.name}] 기술 아키텍처 설계 완료")
            stack = result.get("recommended_stack", {})
            logger.debug(f"  - Frontend: {stack.get('frontend', 'N/A')}")
            logger.debug(f"  - Backend: {stack.get('backend', 'N/A')}")

            return result

        except Exception as e:
            logger.error(f"[{self.name}] 기술 아키텍처 설계 실패: {e}")
            return self._get_fallback_architecture(service_overview)

    def _get_fallback_architecture(self, service_overview: str) -> Dict[str, Any]:
        """Fallback 기술 아키텍처"""
        return {
            "recommended_stack": {
                "frontend": "React.js with TypeScript",
                "backend": "Node.js with NestJS",
                "database": "PostgreSQL",
                "infrastructure": "AWS (Elastic Beanstalk, RDS, S3, CloudFront)",
                "reasoning": "확장성과 개발 생산성을 고려한 모던 스택"
            },
            "architecture_desc": "클라우드 네이티브 3-Tier 아키텍처. React SPA + REST API + RDB 구조로 MVP 빠른 개발 가능.",
            "technical_challenges": [
                "실시간 기능 구현 (WebSocket)",
                "대용량 트래픽 처리 (Auto Scaling)",
                "데이터 일관성 보장"
            ],
            "roadmap": {
                "phase1_mvp": "Phase 1 (3개월): 핵심 기능 MVP, 기본 사용자 인증, 메인 서비스 플로우",
                "phase2_scale": "Phase 2 (3개월): 알림 시스템, 소셜 기능, 결제 연동",
                "phase3_optimize": "Phase 3 (3개월): 성능 최적화, AI 기능 추가, B2B 확장"
            }
        }

    def format_as_markdown(self, architecture: Dict[str, Any]) -> str:
        """기술 아키텍처를 마크다운 형식으로 변환"""
        md = "### 기술 스택\n\n"

        stack = architecture.get("recommended_stack", {})
        md += f"- **Frontend**: {stack.get('frontend', 'N/A')}\n"
        md += f"- **Backend**: {stack.get('backend', 'N/A')}\n"
        md += f"- **Database**: {stack.get('database', 'N/A')}\n"
        md += f"- **Infrastructure**: {stack.get('infrastructure', 'N/A')}\n\n"

        if stack.get("reasoning"):
            md += f"> {stack.get('reasoning')}\n\n"

        # 아키텍처 설명
        arch_desc = architecture.get("architecture_desc", "")
        if arch_desc:
            md += "### 시스템 아키텍처\n\n"
            md += f"{arch_desc}\n\n"

        # 기술적 난관
        challenges = architecture.get("technical_challenges", [])
        if challenges:
            md += "### 기술적 도전 과제\n\n"
            for c in challenges[:5]:
                md += f"- {c}\n"
            md += "\n"

        # 개발 로드맵
        roadmap = architecture.get("roadmap", {})
        if roadmap:
            md += "### 개발 로드맵\n\n"
            if roadmap.get("phase1_mvp"):
                md += f"**{roadmap['phase1_mvp']}**\n\n"
            if roadmap.get("phase2_scale"):
                md += f"**{roadmap['phase2_scale']}**\n\n"
            if roadmap.get("phase3_optimize"):
                md += f"**{roadmap['phase3_optimize']}**\n\n"

        return md


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    agent = TechArchitectAgent()
    result = agent._get_fallback_architecture("러닝 앱")
    print(agent.format_as_markdown(result))
