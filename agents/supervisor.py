"""
PlanCraft - LangGraph Native Supervisor (오케스트레이터)

전문 에이전트(Specialists)들의 작업을 조율하고 관리하는 지휘자 역할을 수행합니다.
모든 전문 에이전트를 무조건 실행하지 않고, 기획 주제에 따라 필요한 전문가만 선별하여 투입합니다.

[Key Architecture]
1. 동적 라우팅 (Dynamic Routing):
   - 입력된 주제를 분석하여 '시장 분석'이 필요한지, '기술 설계'가 필요한지 등을 AI가 실시간으로 판단합니다.
   - 예: "단순 아이디어" -> Market Agent 생략 가능, "플랫폼 구축" -> Tech Agent 필수 호출.
2. 비동기 병렬 실행 (Async Parallel Execution):
   - 의존성이 없는 작업들(예: 시장 분석 vs 기술 검토)은 동시에 실행하여 전체 대기 시간을 단축합니다.
3. 데이터 통합 (Context Aggregation):
   - 각 전문가가 산출한 데이터를 취합하여 Writer가 활용할 수 있는 단일 컨텍스트로 가공합니다.
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

from agents.supervisor_types import (
    AgentExecutionStats,
    ExecutionStats,
    LambdaAgent,
    RoutingDecision,
    detect_required_agents
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
        purpose: str = "기획서 작성",
        use_llm_routing: bool = False  # [REFACTOR] 기본값 False로 변경
    ) -> RoutingDecision:
        """
        필요한 에이전트 결정 (규칙 기반 기본, LLM 옵션)

        [REFACTOR] LLM 판단 범위 축소:
        - 기본: 규칙 기반 결정론적 라우팅 (테스트 가능, 일관성 보장)
        - 옵션: use_llm_routing=True 시 LLM 기반 동적 라우팅

        Args:
            service_overview: 서비스 개요
            purpose: 분석 목적
            use_llm_routing: True면 LLM 사용 (기본 False)

        Returns:
            RoutingDecision: 라우팅 결정
        """
        logger.info("[NativeSupervisor] 🧭 라우팅 결정 시작...")

        # 규칙 기반 라우팅 (기본)
        if not use_llm_routing:
            decision = detect_required_agents(service_overview, purpose)
            logger.info(f"[NativeSupervisor] 규칙 기반 라우팅: {decision.required_analyses}")
            logger.info(f"[NativeSupervisor] 결정 이유: {decision.reasoning}")
            return decision

        # LLM 기반 라우팅 (옵션 - 고급 사용 시)
        logger.info("[NativeSupervisor] LLM 기반 라우팅 사용")
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
            logger.info(f"[NativeSupervisor] LLM 라우팅 결정: {decision.required_analyses}")
            logger.info(f"[NativeSupervisor] 결정 이유: {decision.reasoning}")
            return decision
        except Exception as e:
            logger.warning(f"[NativeSupervisor] LLM 라우팅 실패, 규칙 기반으로 전환: {e}")
            # LLM 실패 시 규칙 기반으로 Fallback
            return detect_required_agents(service_overview, purpose)
    
    
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
        user_constraints: List[str] = None,
        use_llm_routing: bool = False,  # [NEW] 규칙 기반 라우팅이 기본
        deep_analysis_mode: bool = False, # [NEW] 심층 분석 모드
        event_callback: callable = None  # [NEW] 이벤트 콜백
    ) -> Dict[str, Any]:
        """
        전문 에이전트 실행 (Plan-and-Execute DAG)

        Args:
            service_overview: 서비스 개요
            target_market: 타겟 시장
            target_users: 타겟 사용자
            tech_stack: 기술 스택
            development_scope: 개발 범위
            web_search_results: 웹 검색 결과
            purpose: 분석 목적
            force_all: True면 모든 필수 에이전트 실행
            user_constraints: 사용자 제약 조건
            use_llm_routing: True면 LLM 기반 라우팅 (기본 False)

        Returns:
            Dict: 에이전트 실행 결과
        """
        logger.info("=" * 60)
        logger.info("[NativeSupervisor] 전문 에이전트 오케스트레이션 시작 (DAG)")

        results = {}

        if force_all:
            required = ["market", "bm", "financial", "risk"]
            reasoning = "강제 전체 분석"
        else:
            decision = self.decide_required_agents(
                service_overview, purpose, use_llm_routing=use_llm_routing
            )
            required = list(decision.required_analyses)
            reasoning = decision.reasoning

            # [NOTE] 규칙 기반 라우팅에서는 이미 기획서 필수 에이전트가 포함됨
            # LLM 라우팅 사용 시에만 추가 검증 필요
            if use_llm_routing and "기획서" in purpose:
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
            "user_constraints": user_constraints or [],
            "deep_analysis_mode": deep_analysis_mode, # [NEW]
            "on_event": event_callback # [NEW] 이벤트 콜백 전달
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

        # [NEW] 이벤트 콜백 추출
        on_event = context.get("on_event")

        # 실패한 에이전트 추적 (Replan용)
        failed_agents = []

        # [NEW] 실행 통계 초기화
        stats = ExecutionStats()
        stats.record_start(
            plan_id=f"plan_{datetime.now().strftime('%H%M%S')}",
            total_agents=len(plan.get_all_agents())
        )

        # 설정 로드
        from utils.settings import settings
        max_workers = settings.MAX_PARALLEL_AGENTS
        timeout = settings.AGENT_TIMEOUT_SEC

        for step in plan.steps:
            logger.info(f"--- 단계 {step.step_id}: {step.description} ---")
            
            # [Event] 단계 시작
            if on_event:
                on_event({
                    "type": "step_start",
                    "step_id": step.step_id,
                    "description": step.description,
                    "agents": step.agent_ids
                })

            # 병렬 실행을 위한 Future 목록
            futures = {}

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for agent_id in step.agent_ids:
                    if agent_id in self.agents:
                        # [NEW] 에이전트 통계 시작
                        agent_stats = stats.get_agent_stats(agent_id)
                        agent_stats.record_start()
                        
                        # [Event] 에이전트 시작
                        if on_event:
                            on_event({
                                "type": "agent_start",
                                "agent_id": agent_id,
                                "timestamp": datetime.now().isoformat()
                            })

                        # 실행 컨텍스트 준비
                        agent_context = self._prepare_agent_context(agent_id, context, results)

                        # 비동기 제출
                        future = executor.submit(self.agents[agent_id].run, **agent_context)
                        futures[future] = agent_id
                        logger.info(f"  🚀 [Running] {agent_id} (Timeout: {timeout}s)...")

                # 완료 대기 및 결과 수집
                for future in as_completed(futures):
                    agent_id = futures[future]
                    agent_stats = stats.get_agent_stats(agent_id)

                    try:
                        # [IMPROVE] 타임아웃 적용
                        result = future.result(timeout=timeout)
                        
                        # 결과 키 매핑 (Registry 기반)
                        result_key = self._get_result_key(agent_id)
                        results[result_key] = result

                        # [NEW] 성공 통계 기록
                        agent_stats.record_end(success=True)
                        logger.info(f"  ✅ [Done] {agent_id} ({agent_stats.execution_time_ms:.0f}ms)")
                        
                        # [Event] 에이전트 완료
                        if on_event:
                            on_event({
                                "type": "agent_success",
                                "agent_id": agent_id,
                                "duration_ms": agent_stats.execution_time_ms
                            })

                    except Exception as e:
                        # [REFACTOR] 에러 카테고리화 적용
                        error_category = categorize_error(e)
                        error_msg = str(e)
                        
                        # 타임아웃 구체화
                        if isinstance(e, TimeoutError):
                            error_category = "TIMEOUT_ERROR"
                            error_msg = f"실행 시간 초과 ({timeout}초)"

                        # [NEW] 에러 통계 기록
                        agent_stats.record_error(error_msg, error_category)

                        # 카테고리별 로깅
                        logger.error(f"  ❌ [{error_category}] {agent_id}: {error_msg}")
                        
                        # [Event] 에이전트 에러
                        if on_event:
                            on_event({
                                "type": "agent_error",
                                "agent_id": agent_id,
                                "error": error_msg,
                                "category": error_category
                            })

                        # [NEW] 동적 Replan: 복구 가능한 에러는 재시도 (TIMEOUT은 재시도하지 않음)
                        if error_category in ["LLM_ERROR", "NETWORK_ERROR"]:
                            retry_result = self._retry_agent(agent_id, context, results, stats)
                            if retry_result:
                                results[self._get_result_key(agent_id)] = retry_result
                                agent_stats.record_end(success=True)
                                logger.info(f"  🔄 [Retried] {agent_id} 재시도 성공 (시도 {agent_stats.retry_count}회)")
                                
                                # [Event] 재시도 성공
                                if on_event:
                                    on_event({
                                        "type": "agent_retry_success",
                                        "agent_id": agent_id
                                    })
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
                        
                        # [Event] Fallback 사용
                        if on_event:
                            on_event({
                                "type": "agent_fallback",
                                "agent_id": agent_id,
                                "reason": fallback.get("_fallback_reason")
                            })

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
            
            # [NEW] 심층 분석 모드
            if base_context.get("deep_analysis_mode", False):
                ctx["analysis_requirements"] = "Provide deep comparative analysis with at least 3 competitors."
            
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
            
            # [NEW] 심층 분석 모드일 경우 추가 지침 전달 (Supervisor run에서 주입된 옵션 사용)
            if base_context.get("deep_analysis_mode", False):
                ctx["analysis_depth"] = "deep"
                ctx["financial_requirements"] = "Provide Best/Normal/Worst case scenarios for financial projections."
            else:
                ctx["analysis_depth"] = "standard"
            
        elif agent_id == "risk":
            ctx["tech_stack"] = base_context.get("tech_stack", "")
            # bm 결과 참조
            ctx["business_model"] = current_results.get("business_model", {})
            
            # [NEW] 심층 분석 모드: Pre-mortem 기법 적용
            if base_context.get("deep_analysis_mode", False):
                ctx["analysis_depth"] = "deep"
                ctx["risk_framework"] = "Pre-mortem Analysis: Assume the project has failed and identify why."
                ctx["additional_requirements"] = "Include a step-by-step contingency plan."
            
        elif agent_id == "tech":
            ctx["target_users"] = base_context.get("target_users", "")
            ctx["user_constraints"] = base_context.get("user_constraints", [])
            
            # [NEW] Adaptive Implementation Mode
            # 서비스 개요와 기술 스택 정보를 확인하여 IT vs Non-IT 판단
            svc_overview = base_context.get("service_overview", "").lower()
            tech_stack_info = base_context.get("tech_stack", "")
            
            is_tech_project = any(k in svc_overview for k in ["앱", "웹", "플랫폼", "ai", "서비스", "개발"])
            if not is_tech_project and "오프라인" in svc_overview: 
                 mode = "operation"
            else: 
                 mode = "tech"

            # 강제 모드 설정 (tech_stack 내용으로 2차 판단)
            if "없음" in tech_stack_info or "해당사항 없음" in tech_stack_info:
                mode = "operation"

            if mode == "tech":
                ctx["focus_area"] = "IT System Architecture & API Specification"
                if base_context.get("deep_analysis_mode", False):
                    ctx["detail_level"] = "high (Include API Endpoints JSON and DB Schema)"
            else:
                ctx["focus_area"] = "Physical Operation Plan & Space Layout"
                ctx["tech_stack"] = "N/A (Non-IT Project)" # 기술 스택 무시
                if base_context.get("deep_analysis_mode", False):
                    ctx["detail_level"] = "high (Include Staffing Schedule and Floor Plan Description)"
            
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

    async def arun(self, *args, **kwargs) -> Dict[str, Any]:
        """
        [NEW] 비동기 실행 래퍼 (LangGraph 호환성)
        
        NativeSupervisor.run()은 내부적으로 ThreadPoolExecutor를 사용하므로
        CPU 바운드보다는 I/O 바운드 작업입니다. 
        asyncio.to_thread를 사용하여 메인 이벤트 루프를 차단하지 않고 실행합니다.
        """
        import asyncio
        return await asyncio.to_thread(self.run, *args, **kwargs)


# 하위 호환성을 위해 alias 제공
PlanSupervisor = NativeSupervisor

if __name__ == "__main__":
    supervisor = NativeSupervisor()
