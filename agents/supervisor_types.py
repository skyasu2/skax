"""
Supervisor Type Definitions & Helper Classes

이 모듈은 agents.supervisor 모듈에서 사용되는 데이터 모델, 통계 클래스, 
그리고 라우팅 결정 로직을 분리하여 순환 참조를 방지하고 유지보수성을 높입니다.
"""

from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel, Field


# =============================================================================
# 실행 통계 (retry/fail 카운터 로깅 강화)
# =============================================================================

@dataclass
class AgentExecutionStats:
    """에이전트 실행 통계 (운영 분석용)"""
    agent_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    success: bool = False
    error_messages: List[str] = field(default_factory=list)
    error_category: str = ""
    fallback_used: bool = False
    execution_time_ms: float = 0.0

    def record_start(self):
        self.started_at = datetime.now()

    def record_end(self, success: bool = True):
        self.completed_at = datetime.now()
        self.success = success
        if self.started_at:
            self.execution_time_ms = (self.completed_at - self.started_at).total_seconds() * 1000

    def record_error(self, error_msg: str, category: str = "UNKNOWN"):
        self.error_messages.append(error_msg)
        self.error_category = category
        self.retry_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "retry_count": self.retry_count,
            "success": self.success,
            "error_messages": self.error_messages,
            "error_category": self.error_category,
            "fallback_used": self.fallback_used,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


@dataclass
class ExecutionStats:
    """전체 실행 통계"""
    plan_id: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_agents: int = 0
    successful_agents: int = 0
    failed_agents: int = 0
    retried_agents: int = 0
    fallback_used_count: int = 0
    agent_stats: Dict[str, AgentExecutionStats] = field(default_factory=dict)

    def record_start(self, plan_id: str, total_agents: int):
        self.plan_id = plan_id
        self.started_at = datetime.now()
        self.total_agents = total_agents

    def record_end(self):
        self.completed_at = datetime.now()
        # 집계
        for stats in self.agent_stats.values():
            if stats.success:
                self.successful_agents += 1
            else:
                self.failed_agents += 1
            if stats.retry_count > 0:
                self.retried_agents += 1
            if stats.fallback_used:
                self.fallback_used_count += 1

    def get_agent_stats(self, agent_id: str) -> AgentExecutionStats:
        if agent_id not in self.agent_stats:
            self.agent_stats[agent_id] = AgentExecutionStats(agent_id=agent_id)
        return self.agent_stats[agent_id]

    def to_summary(self) -> str:
        """실행 통계 요약 (로그용)"""
        duration = 0
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()

        lines = [
            "=" * 50,
            f"📊 실행 통계 요약 (Plan: {self.plan_id})",
            "=" * 50,
            f"총 에이전트: {self.total_agents}",
            f"✅ 성공: {self.successful_agents}",
            f"❌ 실패: {self.failed_agents}",
            f"🔄 재시도: {self.retried_agents}",
            f"⚠️ Fallback: {self.fallback_used_count}",
            f"⏱️ 총 소요시간: {duration:.2f}초",
        ]

        # 실패한 에이전트 상세
        failed = [s for s in self.agent_stats.values() if not s.success]
        if failed:
            lines.append("-" * 50)
            lines.append("실패 에이전트 상세:")
            for s in failed:
                lines.append(f"  - {s.agent_id}: {s.error_category} (재시도 {s.retry_count}회)")
                if s.error_messages:
                    lines.append(f"    마지막 에러: {s.error_messages[-1][:100]}")

        lines.append("=" * 50)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_agents": self.total_agents,
            "successful_agents": self.successful_agents,
            "failed_agents": self.failed_agents,
            "retried_agents": self.retried_agents,
            "fallback_used_count": self.fallback_used_count,
            "agent_stats": {k: v.to_dict() for k, v in self.agent_stats.items()},
        }


# =============================================================================
# Helper Function Wrapper
# =============================================================================

class LambdaAgent:
    """함수 기반 에이전트를 클래스처럼 래핑"""
    def __init__(self, run_func):
        self.run_func = run_func
        
    def run(self, **kwargs):
        return self.run_func(kwargs)
    
    def format_as_markdown(self, result: Dict[str, Any]) -> str:
        """간단한 JSON to Markdown 변환"""
        if "error" in result:
            return f"Error: {result['error']}"
            
        md = ""
        for k, v in result.items():
            title = k.replace('_', ' ').title()
            md += f"#### {title}\n"
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    md += f"- **{sub_k}**: {sub_v}\n"
            elif isinstance(v, list):
                for item in v:
                    md += f"- {item}\n"
            else:
                md += f"{v}\n"
            md += "\n"
        return md


# =============================================================================
# Router Decision Schema
# =============================================================================

class RoutingDecision(BaseModel):
    """Supervisor 라우팅 결정"""
    required_analyses: List[Literal["market", "bm", "financial", "risk", "tech", "content"]] = Field(
        description="필요한 분석 유형 목록"
    )
    reasoning: str = Field(
        description="라우팅 결정 이유"
    )
    priority_order: List[str] = Field(
        default_factory=list,
        description="실행 우선순위 (의존성 고려)"
    )


# =============================================================================
# 규칙 기반 라우팅 (Deterministic Routing)
# =============================================================================
# [REFACTOR] LLM 판단 범위 축소: 구조적 판단은 코드로 고정

# 선택적 에이전트 활성화 키워드
TECH_KEYWORDS = frozenset([
    "앱", "웹", "플랫폼", "개발", "ai", "블록체인", "기술", "시스템",
    "아키텍처", "api", "서버", "클라우드", "모바일", "ios", "android",
    "react", "node", "python", "aws", "gcp", "azure", "saas", "paas",
    "머신러닝", "딥러닝", "데이터", "알고리즘", "소프트웨어", "하드웨어"
])

CONTENT_KEYWORDS = frozenset([
    "커뮤니티", "sns", "마케팅", "콘텐츠", "브랜드", "홍보", "광고",
    "인플루언서", "크리에이터", "미디어", "유튜브", "인스타", "틱톡",
    "블로그", "뉴스레터", "소셜", "바이럴", "캠페인", "pr", "seo"
])


def detect_required_agents(
    service_overview: str,
    purpose: str = "기획서 작성"
) -> RoutingDecision:
    """
    규칙 기반 에이전트 결정 (Deterministic)

    구조적 판단을 코드로 고정하여 테스트 가능성과 일관성을 보장합니다.

    Rules:
        1. 기획서 목적: market, bm, financial, risk 필수
        2. 아이디어 검증: market, bm만 필요
        3. tech: 기술 관련 키워드 포함 시 추가
        4. content: 마케팅/콘텐츠 관련 키워드 포함 시 추가

    Args:
        service_overview: 서비스 개요 텍스트
        purpose: 분석 목적 ("기획서 작성" | "아이디어 검증" | ...)

    Returns:
        RoutingDecision: 결정론적 라우팅 결과

    Example:
        >>> decision = detect_required_agents("AI 기반 점심 추천 앱", "기획서 작성")
        >>> assert "market" in decision.required_analyses
        >>> assert "tech" in decision.required_analyses  # "AI", "앱" 키워드 감지
    """
    text_lower = service_overview.lower()
    reasons = []

    # 1. 필수 에이전트 결정 (목적 기반)
    if "기획서" in purpose:
        required = ["market", "bm", "financial", "risk"]
        reasons.append("기획서 작성 목적 → 4대 필수 분석 포함")
    else:
        required = ["market", "bm"]
        reasons.append("아이디어 검증 목적 → 시장/BM 분석만 수행")

    # 2. 선택적 에이전트 (키워드 기반)
    # tech 감지
    tech_matches = [kw for kw in TECH_KEYWORDS if kw in text_lower]
    if tech_matches:
        required.append("tech")
        reasons.append(f"기술 키워드 감지: {tech_matches[:3]}")

    # content 감지
    content_matches = [kw for kw in CONTENT_KEYWORDS if kw in text_lower]
    if content_matches:
        required.append("content")
        reasons.append(f"콘텐츠 키워드 감지: {content_matches[:3]}")

    return RoutingDecision(
        required_analyses=required,
        reasoning=" | ".join(reasons),
        priority_order=required
    )
