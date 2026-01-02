"""
PlanCraft - LangGraph 네이티브 Supervisor (개선된 버전)

베스트 프랙티스 적용:
1. Tool 기반 Handoff 패턴
2. 동적 라우팅 (LLM이 필요한 에이전트 결정)
3. create_react_agent 활용
4. 명시적 상태 관리

아키텍처:
    User Input
        ↓
    Supervisor (Router)
        ↓ (동적 결정)
    ┌───┴───┬───────┬───────┐
    ↓       ↓       ↓       ↓ (Tech, Content 포함)
  Market   BM   Tech   Content
    ↓       ↓       ↓       ↓
    └───────┴───┬───┴───────┘
                ↓
    Result Integration
        ↓
    Writer Context
"""

from typing import Dict, Any, List, Optional, Literal, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.llm import get_llm
from utils.file_logger import FileLogger

logger = FileLogger()


# =============================================================================
# 실행 통계 (retry/fail 카운터 로깅 강화)
# =============================================================================

@dataclass
class AgentExecutionStats:
    """에이전트 실행 통계 (운영 분석용)"""
    agent_id: str
    started_at: datetime = None
    completed_at: datetime = None
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
    started_at: datetime = None
    completed_at: datetime = None
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


# [NEW] LambdaAgent를 최상위에 정의
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
# LangGraph Native Supervisor
# =============================================================================

class NativeSupervisor:
    """
    LangGraph 네이티브 Supervisor (Plan-and-Execute 패턴)

    전문 에이전트들을 조율하여 사업 기획서 분석을 수행합니다.
    DAG 기반 병렬 실행, 동적 라우팅, 에러 복구를 지원합니다.

    Features:
        - Agent Registry 기반 Factory 패턴
        - DAG 기반 병렬 실행 (Topological Sort)
        - LLM 라우팅 (필요한 에이전트 동적 결정)
        - 에러 복구 (재시도 + Fallback)
        - 실행 통계 (retry/fail 카운터)

    Attributes:
        llm: LLM 인스턴스
        agents: 초기화된 에이전트 딕셔너리
        agent_registry: 에이전트 스펙 레지스트리

    Example:
        >>> from agents.supervisor import NativeSupervisor
        >>>
        >>> # 1. Supervisor 초기화
        >>> supervisor = NativeSupervisor()
        >>>
        >>> # 2. 서비스 분석 실행
        >>> results = supervisor.run(
        ...     service_overview="점심 메뉴 추천 앱",
        ...     target_market="직장인",
        ...     purpose="기획서 작성"
        ... )
        >>>
        >>> # 3. 결과 확인
        >>> print(results["market_analysis"])  # 시장 분석
        >>> print(results["business_model"])    # 비즈니스 모델
        >>> print(results["integrated_context"]) # 통합 컨텍스트

    Note:
        - 기획서 목적 시 market, bm, financial, risk 필수 포함
        - 실행 통계는 results["_execution_stats"]에 저장
        - Mermaid 그래프는 export_plan_to_mermaid()로 생성

    See Also:
        - agents.agent_config: 에이전트 레지스트리
        - agents.agent_config.resolve_execution_plan_dag: DAG 생성
        - agents.agent_config.export_plan_to_mermaid: Mermaid 변환
    """
    
    ROUTER_SYSTEM_PROMPT = """당신은 사업 기획서 분석 작업을 조율하는 Supervisor입니다.

사용자의 서비스 아이디어를 분석하여, 어떤 전문 분석이 필요한지 결정하세요.

## 사용 가능한 분석 유형 (6개)

### 핵심 분석 (대부분 필요)
1. **market**: 시장 분석 - TAM/SAM/SOM 시장 규모, 경쟁사 분석, 트렌드
2. **bm**: 비즈니스 모델 - 수익화 전략, 가격 정책, 해자(Moat) 설계
3. **financial**: 재무 계획 - 초기 투자비, 월별 손익, BEP 계산
4. **risk**: 리스크 분석 - 기술/법률/시장/운영 리스크 및 대응 전략

### 선택적 분석 (조건부)
5. **tech**: 기술 아키텍처 - 기술 스택, 시스템 설계, 개발 로드맵
   - 조건: 앱/웹/플랫폼 개발, AI/블록체인 등 특수 기술 포함 시
6. **content**: 콘텐츠 전략 - 브랜딩, 마케팅, 사용자 유입 전략
   - 조건: 커뮤니티/SNS 운영, 콘텐츠 마케팅 필요 시

## 판단 원칙

### 기본 규칙
- **기획서 작성**: market, bm, financial, risk 모두 필수
- **아이디어 검증만**: market, bm으로 충분

### 추가 판단
- IT 서비스/플랫폼: + tech
- 커뮤니티/미디어: + content
- 앱/웹 개발 명시: + tech
- 마케팅/홍보 중요: + content

### 의존성 (실행 순서에 영향)
- bm → market 분석 후 수행
- financial → bm 결과 참조
- risk → bm 결과 참조
- content → market(타겟) 참조
- tech → 독립적 실행 가능

## 출력 예시
- 사업 기획서: ["market", "bm", "financial", "risk"]
- IT 서비스 기획서: ["market", "bm", "financial", "risk", "tech"]
- 커뮤니티 플랫폼: ["market", "bm", "financial", "risk", "tech", "content"]
- 단순 아이디어 검토: ["market", "bm"]

**주의**: 기획서 목적이면 financial, risk를 생략하지 마세요!
"""

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.3)
        self.router_llm = self.llm.with_structured_output(RoutingDecision)

        # [REFACTOR] Config 기반 에이전트 로드 (Factory Registry 활용)
        from agents.agent_config import (
            AGENT_REGISTRY,
            get_routing_prompt,
            get_result_key,
            create_agent,
        )
        self.agent_registry = AGENT_REGISTRY
        self.routing_prompt = get_routing_prompt()
        self._get_result_key = get_result_key  # [NEW] Registry 기반 함수 사용
        self._create_agent = create_agent      # [NEW] Factory 함수 사용

        # 전문 에이전트 동적 초기화
        self.agents = {}
        self._init_agents()

        logger.info(f"[NativeSupervisor] 초기화 완료 (에이전트 {len(self.agents)}개)")

    def _init_agents(self):
        """
        [REFACTOR] Factory Registry 기반 에이전트 초기화

        개선사항:
        1. 하드코딩된 class_path 제거 → AGENT_REGISTRY.class_path 사용
        2. 동적 import 로직 캡슐화 → create_agent() 함수 사용
        3. 새 에이전트 추가 시 AGENT_REGISTRY만 수정하면 됨
        """
        for agent_id in self.agent_registry.keys():
            try:
                agent = self._create_agent(agent_id, llm=self.llm)
                if agent:
                    self.agents[agent_id] = agent
                    logger.info(f"  - {agent_id} 초기화 완료")
                else:
                    logger.warning(f"  - {agent_id} 초기화 스킵 (class_path 미설정)")
            except Exception as e:
                logger.error(f"  - {agent_id} 초기화 실패: {e}")

    
    def decide_required_agents(
        self,
        service_overview: str,
        purpose: str = "기획서 작성"
    ) -> RoutingDecision:
        """동적 라우팅: 필요한 에이전트 결정"""
        logger.info("[NativeSupervisor] 🧭 라우팅 결정 시작...")
        
        messages = [
            SystemMessage(content=self.ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=f"""## 서비스 개요
{service_overview}

## 분석 목적
{purpose}

위 내용을 바탕으로 어떤 분석이 필요한지 결정하세요.
""")
        ]
        
        try:
            decision = self.router_llm.invoke(messages)
            logger.info(f"[NativeSupervisor] 라우팅 결정: {decision.required_analyses}")
            logger.info(f"[NativeSupervisor] 결정 이유: {decision.reasoning}")
            return decision
        except Exception as e:
            logger.error(f"[NativeSupervisor] 라우팅 실패, 전체 분석 수행: {e}")
            return RoutingDecision(
                required_analyses=["market", "bm", "financial", "risk"],
                reasoning="라우팅 실패로 전체 분석 수행",
                priority_order=["market", "bm", "financial", "risk"]
            )
    
    
    def run(
        self,
        service_overview: str,
        target_market: str = "",
        target_users: str = "",
        tech_stack: str = "React Native + Node.js",
        development_scope: str = "MVP 3개월",
        web_search_results: List[Dict[str, Any]] = None,
        purpose: str = "기획서 작성",
        force_all: bool = False,
        user_constraints: List[str] = None  # [NEW]
    ) -> Dict[str, Any]:
        """전문 에이전트 실행 (Plan-and-Execute DAG)"""
        logger.info("=" * 60)
        logger.info("[NativeSupervisor] 전문 에이전트 오케스트레이션 시작 (DAG)")
        
        results = {}
        
        if force_all:
            required = ["market", "bm", "financial", "risk"]
            reasoning = "강제 전체 분석"
        else:
            decision = self.decide_required_agents(service_overview, purpose)
            required = list(decision.required_analyses)
            reasoning = decision.reasoning

            # [FIX] 기획서 목적일 때 financial/risk 필수 포함
            # LLM Router가 조건부로 판단해도 기획서에는 필수 섹션임
            if "기획서" in purpose:
                must_have = ["market", "bm", "financial", "risk"]
                missing = [a for a in must_have if a not in required]
                if missing:
                    logger.info(f"[NativeSupervisor] 기획서 필수 에이전트 추가: {missing}")
                    required = list(set(required) | set(must_have))
                    reasoning += f" (기획서 필수 추가: {missing})"
        
        # DAG 기반 실행 계획 수립
        from agents.agent_config import resolve_execution_plan_dag
        execution_plan = resolve_execution_plan_dag(required, reasoning)
        
        results["_plan"] = execution_plan
        
        # 단계별 병렬 실행
        self._execute_plan(execution_plan, results, {
            "service_overview": service_overview,
            "target_market": target_market,
            "target_users": target_users,
            "tech_stack": tech_stack,
            "development_scope": development_scope,
            "web_search_results": web_search_results,
            "user_constraints": user_constraints or []
        })
        
        results["integrated_context"] = self._integrate_results(results)
        
        logger.info("[NativeSupervisor] 오케스트레이션 완료")
        return results

    def _execute_plan(self, plan, results: Dict, context: Dict):
        """
        실행 계획에 따라 단계별 병렬 실행 (동적 Replan 지원)

        [REFACTOR] 동적 Replan 패턴 적용:
        - 에이전트 실패 시 재시도 또는 대체 전략 수립
        - 복구 가능한 에러(LLM_ERROR, NETWORK_ERROR)는 1회 재시도
        - 치명적 에러(VALIDATION_ERROR)는 Fallback 데이터 사용

        Exception 카테고리화:
        - LLM_ERROR, NETWORK_ERROR: 재시도 가능
        - VALIDATION_ERROR, UNKNOWN: 재시도 불가, Fallback 사용

        [NEW] 실행 통계 기록:
        - 각 에이전트별 시작/종료 시간, 재시도 횟수, 에러 메시지 추적
        - 전체 실행 요약 로그 출력
        """
        from utils.error_handler import categorize_error

        # 실패한 에이전트 추적 (Replan용)
        failed_agents = []

        # [NEW] 실행 통계 초기화
        stats = ExecutionStats()
        stats.record_start(
            plan_id=f"plan_{datetime.now().strftime('%H%M%S')}",
            total_agents=len(plan.get_all_agents())
        )

        for step in plan.steps:
            logger.info(f"--- 단계 {step.step_id}: {step.description} ---")

            # 병렬 실행을 위한 Future 목록
            futures = {}

            with ThreadPoolExecutor() as executor:
                for agent_id in step.agent_ids:
                    if agent_id in self.agents:
                        # [NEW] 에이전트 통계 시작
                        agent_stats = stats.get_agent_stats(agent_id)
                        agent_stats.record_start()

                        # 실행 컨텍스트 준비
                        agent_context = self._prepare_agent_context(agent_id, context, results)

                        # 비동기 제출
                        future = executor.submit(self.agents[agent_id].run, **agent_context)
                        futures[future] = agent_id
                        logger.info(f"  🚀 [Running] {agent_id}...")

                # 완료 대기 및 결과 수집
                for future in as_completed(futures):
                    agent_id = futures[future]
                    agent_stats = stats.get_agent_stats(agent_id)

                    try:
                        result = future.result()
                        # 결과 키 매핑 (Registry 기반)
                        result_key = self._get_result_key(agent_id)
                        results[result_key] = result

                        # [NEW] 성공 통계 기록
                        agent_stats.record_end(success=True)
                        logger.info(f"  ✅ [Done] {agent_id} ({agent_stats.execution_time_ms:.0f}ms)")

                    except Exception as e:
                        # [REFACTOR] 에러 카테고리화 적용
                        error_category = categorize_error(e)
                        error_msg = str(e)

                        # [NEW] 에러 통계 기록
                        agent_stats.record_error(error_msg, error_category)

                        # 카테고리별 로깅
                        logger.error(f"  ❌ [{error_category}] {agent_id}: {error_msg}")

                        # [NEW] 동적 Replan: 복구 가능한 에러는 재시도
                        if error_category in ["LLM_ERROR", "NETWORK_ERROR"]:
                            retry_result = self._retry_agent(agent_id, context, results, stats)
                            if retry_result:
                                results[self._get_result_key(agent_id)] = retry_result
                                agent_stats.record_end(success=True)
                                logger.info(f"  🔄 [Retried] {agent_id} 재시도 성공 (시도 {agent_stats.retry_count}회)")
                                continue

                        # 재시도 실패 또는 복구 불가 에러
                        failed_agents.append(agent_id)
                        agent_stats.record_end(success=False)
                        agent_stats.fallback_used = True

                        # [NEW] Fallback 데이터 사용
                        fallback = self._get_fallback_result(agent_id, context)
                        results[self._get_result_key(agent_id)] = {
                            "error": error_msg,
                            "error_category": error_category,
                            "agent_id": agent_id,
                            "fallback_used": True,
                            "retry_count": agent_stats.retry_count,
                            **fallback
                        }
                        logger.warning(f"  ⚠️ [Fallback] {agent_id} Fallback 데이터 사용 (재시도 {agent_stats.retry_count}회 실패)")

        # [NEW] 동적 Replan: 실패한 에이전트가 있으면 의존 에이전트 체크
        if failed_agents:
            self._handle_failed_dependencies(failed_agents, plan, results, context)

        # [NEW] 실행 통계 완료 및 로깅
        stats.record_end()
        logger.info(stats.to_summary())

        # 결과에 통계 포함
        results["_execution_stats"] = stats.to_dict()

    def _retry_agent(
        self,
        agent_id: str,
        context: Dict,
        results: Dict,
        stats: ExecutionStats = None,
        max_retries: int = 1
    ) -> Optional[Dict]:
        """
        실패한 에이전트 재시도 (동적 Replan 패턴)

        Args:
            agent_id: 재시도할 에이전트 ID
            context: 실행 컨텍스트
            results: 현재까지의 결과
            stats: 실행 통계 (재시도 횟수 기록용)
            max_retries: 최대 재시도 횟수

        Returns:
            성공 시 결과 Dict, 실패 시 None
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"  🔄 [Retry {attempt + 1}/{max_retries}] {agent_id}...")
                agent_context = self._prepare_agent_context(agent_id, context, results)
                result = self.agents[agent_id].run(**agent_context)
                return result
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"  ⚠️ [Retry Failed] {agent_id}: {error_msg}")
                # [NEW] 재시도 실패도 통계에 기록
                if stats:
                    from utils.error_handler import categorize_error
                    stats.get_agent_stats(agent_id).record_error(error_msg, categorize_error(e))
        return None

    def _get_fallback_result(self, agent_id: str, context: Dict, error_msg: str = "") -> Dict:
        """
        에이전트 실패 시 Fallback 결과 생성

        각 에이전트별로 최소한의 유효한 데이터 구조와 사용자 친화적 메시지를 반환합니다.

        Returns:
            Dict: fallback 데이터 + 메타 정보
                - _fallback_reason: 사용자에게 표시할 실패 이유
                - _fallback_guidance: 후속 조치 안내
                - _fallback_severity: 심각도 (info/warning/error)
        """
        service = context.get("service_overview", "서비스")[:50]

        # 에이전트별 사용자 친화적 메시지
        user_messages = {
            "market": {
                "reason": "시장 분석 데이터를 수집하지 못했습니다",
                "guidance": "외부 시장 조사 자료를 첨부하시면 더 정확한 분석이 가능합니다",
                "severity": "warning",
            },
            "bm": {
                "reason": "비즈니스 모델 분석에 필요한 정보가 부족합니다",
                "guidance": "수익 구조나 가격 정책에 대한 추가 정보를 제공해주세요",
                "severity": "warning",
            },
            "financial": {
                "reason": "재무 분석을 위한 데이터가 충분하지 않습니다",
                "guidance": "예상 비용, 매출 목표 등 재무 관련 정보를 추가해주세요",
                "severity": "info",
            },
            "risk": {
                "reason": "리스크 분석 중 오류가 발생했습니다",
                "guidance": "기본적인 리스크 요소만 포함됩니다. 상세 분석이 필요하면 재시도해주세요",
                "severity": "warning",
            },
            "tech": {
                "reason": "기술 스택 분석에 실패했습니다",
                "guidance": "원하시는 기술 스택이나 개발 환경을 직접 명시해주세요",
                "severity": "info",
            },
            "content": {
                "reason": "콘텐츠 전략 분석에 실패했습니다",
                "guidance": "타겟 고객층이나 마케팅 채널에 대한 정보를 추가해주세요",
                "severity": "info",
            },
        }

        # 에이전트별 Fallback 데이터
        fallback_data = {
            "market": {
                "tam": {"value": "추가 분석 필요", "description": f"{service} 관련 전체 시장"},
                "sam": {"value": "추가 분석 필요", "description": "접근 가능 시장 규모"},
                "som": {"value": "추가 분석 필요", "description": "획득 목표 시장"},
                "competitors": [],
                "trends": ["시장 트렌드 데이터 수집 필요"],
            },
            "bm": {
                "revenue_model": "수익 모델 정의 필요",
                "pricing": {"strategy": "가격 전략 수립 필요", "tiers": []},
                "moat": "경쟁 우위 요소 분석 필요",
            },
            "financial": {
                "initial_investment": "초기 투자 규모 산정 필요",
                "monthly_pl": "월간 손익 예측 필요",
                "bep": "손익분기점 분석 필요",
                "funding_strategy": "자금 조달 전략 수립 필요",
            },
            "risk": {
                "risks": [
                    {"category": "운영", "description": "운영 리스크 분석 필요", "probability": "중", "impact": "중"},
                    {"category": "시장", "description": "시장 리스크 분석 필요", "probability": "중", "impact": "중"},
                ],
                "mitigation": "리스크 대응 전략 수립 필요",
            },
            "tech": {
                "recommended_stack": ["기술 스택 선정 필요"],
                "architecture_desc": "시스템 아키텍처 설계 필요",
                "infrastructure": "인프라 구성 계획 필요",
            },
            "content": {
                "brand_concept": "브랜드 컨셉 개발 필요",
                "acquisition_strategy": "고객 유입 전략 수립 필요",
                "content_pillars": ["콘텐츠 방향성 정의 필요"],
            },
        }

        # 기본 메시지
        default_message = {
            "reason": f"{agent_id} 분석 중 오류가 발생했습니다",
            "guidance": "잠시 후 다시 시도하거나 관련 정보를 추가해주세요",
            "severity": "warning",
        }

        # 결과 조합
        msg = user_messages.get(agent_id, default_message)
        data = fallback_data.get(agent_id, {"note": "분석 데이터 없음"})

        return {
            **data,
            "_fallback_reason": msg["reason"],
            "_fallback_guidance": msg["guidance"],
            "_fallback_severity": msg["severity"],
            "_original_error": error_msg[:200] if error_msg else None,
        }

    def _handle_failed_dependencies(self, failed_agents: List[str], plan, results: Dict, context: Dict):
        """
        실패한 에이전트의 의존 에이전트 처리 (동적 Replan)

        의존성 그래프를 확인하여 실패한 에이전트에 의존하는 후속 에이전트가 있으면
        해당 에이전트도 Fallback 처리하거나 경고 로깅
        """
        from agents.agent_config import get_dependency_graph

        dep_graph = get_dependency_graph()

        for agent_id, deps in dep_graph.items():
            # 실패한 에이전트에 의존하는 경우
            failed_deps = [d for d in deps if d in failed_agents]
            if failed_deps:
                result_key = self._get_result_key(agent_id)
                # 이미 결과가 있으면 스킵
                if result_key in results and "error" not in results.get(result_key, {}):
                    continue

                logger.warning(f"  ⚠️ [Dependency] {agent_id}의 의존 에이전트 {failed_deps} 실패")
                # 결과에 의존성 실패 정보 추가
                if result_key in results:
                    results[result_key]["dependency_failed"] = failed_deps

    def _prepare_agent_context(self, agent_id: str, base_context: Dict, current_results: Dict) -> Dict:
        """각 에이전트에 필요한 입력 파라미터 구성"""
        ctx = {"service_overview": base_context["service_overview"]}
        
        if agent_id == "market":
            ctx["target_market"] = base_context.get("target_market", "")
            ctx["web_search_results"] = base_context.get("web_search_results")
            
        elif agent_id == "bm":
            ctx["target_users"] = base_context.get("target_users", "")
            # market 결과 참조
            market_res = current_results.get("market_analysis", {})
            ctx["competitors"] = market_res.get("competitors", [])
            
        elif agent_id == "financial":
            ctx["development_scope"] = base_context.get("development_scope", "")
            # bm, market 결과 참조
            ctx["business_model"] = current_results.get("business_model", {})
            ctx["market_analysis"] = current_results.get("market_analysis", {})
            
        elif agent_id == "risk":
            ctx["tech_stack"] = base_context.get("tech_stack", "")
            # bm 결과 참조
            ctx["business_model"] = current_results.get("business_model", {})
            
        elif agent_id == "tech":
            ctx["target_users"] = base_context.get("target_users", "")
            ctx["user_constraints"] = base_context.get("user_constraints", [])
            
        elif agent_id == "content":
            ctx["target_users"] = base_context.get("target_users", "")
            ctx["market_analysis"] = current_results.get("market_analysis", {})
            
        return ctx

    # [REMOVED] _get_result_key 하드코딩 제거
    # 이제 __init__에서 agents.agent_config.get_result_key를 self._get_result_key로 바인딩
    # → AGENT_REGISTRY.result_key 필드를 사용하여 확장성 확보
        
    def _integrate_results(self, results: Dict[str, Any]) -> str:
        """
        전문 에이전트 결과를 마크다운으로 통합 (Registry 기반 동적 통합)
        
        [REFACTOR] 하드코딩된 에이전트 순서 제거 → AGENT_REGISTRY 기반 반복 처리
        새로운 에이전트가 Registry에 추가되면 자동으로 결과에 포함됩니다.
        """
        integrated = "## 전문 에이전트 분석 결과\n\n"
        
        # Registry 순서대로 처리 (market -> bm -> financial ...)
        # AGENT_REGISTRY는 Python 3.7+부터 삽입 순서 보장 (정의된 순서대로 출력됨)
        for agent_id, spec in self.agent_registry.items():
            result_key = spec.result_key
            result_data = results.get(result_key)
            
            if result_data:
                # 에이전트 이름과 결과 포맷팅
                # 예: ### 📊 시장 분석 (Market Agent)
                icon = getattr(spec, "icon", "📄")  # 아이콘이 설정을 따르거나 기본값
                name = getattr(spec, "name", agent_id.upper())
                
                integrated += f"### {icon} {name}\n\n"
                
                # 포맷터 사용 (Agent 인스턴스의 format_as_markdown)
                if agent_id in self.agents:
                    integrated += self.agents[agent_id].format_as_markdown(result_data)
                else:
                    # Fallback 포맷터
                    import json
                    integrated += f"```json\n{json.dumps(result_data, ensure_ascii=False, indent=2)}\n```"
                
                integrated += "\n\n"
                
        # [Backup] Registry에 없는 키가 혹시 있다면 (하위호환성)
        known_keys = [spec.result_key for spec in self.agent_registry.values()]
        for k, v in results.items():
            if k not in known_keys and not k.startswith("_") and isinstance(v, dict):
                 integrated += f"### 📦 기타 분석 ({k})\n\n"
                 integrated += str(v) + "\n\n"

        return integrated


# 하위 호환성을 위해 alias 제공
PlanSupervisor = NativeSupervisor

if __name__ == "__main__":
    supervisor = NativeSupervisor()
