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
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.llm import get_llm
from utils.file_logger import FileLogger

logger = FileLogger()


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
    LangGraph 네이티브 Supervisor
    
    Tool 기반 Handoff + 동적 라우팅 구현
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
        """
        from utils.error_handler import categorize_error

        # 실패한 에이전트 추적 (Replan용)
        failed_agents = []

        for step in plan.steps:
            logger.info(f"--- 단계 {step.step_id}: {step.description} ---")

            # 병렬 실행을 위한 Future 목록
            futures = {}

            with ThreadPoolExecutor() as executor:
                for agent_id in step.agent_ids:
                    if agent_id in self.agents:
                        # 실행 컨텍스트 준비
                        agent_context = self._prepare_agent_context(agent_id, context, results)

                        # 비동기 제출
                        future = executor.submit(self.agents[agent_id].run, **agent_context)
                        futures[future] = agent_id
                        logger.info(f"  🚀 [Running] {agent_id}...")

                # 완료 대기 및 결과 수집
                for future in as_completed(futures):
                    agent_id = futures[future]
                    try:
                        result = future.result()
                        # 결과 키 매핑 (Registry 기반)
                        result_key = self._get_result_key(agent_id)
                        results[result_key] = result
                        logger.info(f"  ✅ [Done] {agent_id}")
                    except Exception as e:
                        # [REFACTOR] 에러 카테고리화 적용
                        error_category = categorize_error(e)
                        error_msg = str(e)

                        # 카테고리별 로깅
                        logger.error(f"  ❌ [{error_category}] {agent_id}: {error_msg}")

                        # [NEW] 동적 Replan: 복구 가능한 에러는 재시도
                        if error_category in ["LLM_ERROR", "NETWORK_ERROR"]:
                            retry_result = self._retry_agent(agent_id, context, results)
                            if retry_result:
                                results[self._get_result_key(agent_id)] = retry_result
                                logger.info(f"  🔄 [Retried] {agent_id} 재시도 성공")
                                continue

                        # 재시도 실패 또는 복구 불가 에러
                        failed_agents.append(agent_id)

                        # [NEW] Fallback 데이터 사용
                        fallback = self._get_fallback_result(agent_id, context)
                        results[self._get_result_key(agent_id)] = {
                            "error": error_msg,
                            "error_category": error_category,
                            "agent_id": agent_id,
                            "fallback_used": True,
                            **fallback
                        }
                        logger.warning(f"  ⚠️ [Fallback] {agent_id} Fallback 데이터 사용")

        # [NEW] 동적 Replan: 실패한 에이전트가 있으면 의존 에이전트 체크
        if failed_agents:
            self._handle_failed_dependencies(failed_agents, plan, results, context)

    def _retry_agent(self, agent_id: str, context: Dict, results: Dict, max_retries: int = 1) -> Optional[Dict]:
        """
        실패한 에이전트 재시도 (동적 Replan 패턴)

        Args:
            agent_id: 재시도할 에이전트 ID
            context: 실행 컨텍스트
            results: 현재까지의 결과
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
                logger.warning(f"  ⚠️ [Retry Failed] {agent_id}: {e}")
        return None

    def _get_fallback_result(self, agent_id: str, context: Dict) -> Dict:
        """
        에이전트 실패 시 Fallback 결과 생성

        각 에이전트별로 최소한의 유효한 데이터 구조 반환
        """
        service = context.get("service_overview", "서비스")[:50]

        fallback_map = {
            "market": {
                "tam": {"value": "분석 불가", "description": f"{service} 관련 시장"},
                "sam": {"value": "분석 불가", "description": "접근 가능 시장"},
                "som": {"value": "분석 불가", "description": "획득 가능 시장"},
                "competitors": [],
                "trends": ["시장 분석 데이터 수집 실패"]
            },
            "bm": {
                "revenue_model": "수익 모델 분석 필요",
                "pricing": {"strategy": "가격 전략 분석 필요"},
                "moat": "경쟁 우위 분석 필요"
            },
            "financial": {
                "initial_investment": "초기 투자 분석 필요",
                "monthly_pl": "손익 분석 필요",
                "bep": "손익분기점 분석 필요"
            },
            "risk": {
                "risks": [{"category": "분석 실패", "description": "리스크 분석 데이터 수집 실패"}],
                "mitigation": "추가 분석 필요"
            },
            "tech": {
                "recommended_stack": ["기술 스택 분석 필요"],
                "architecture_desc": "아키텍처 분석 필요"
            },
            "content": {
                "brand_concept": "브랜딩 분석 필요",
                "acquisition_strategy": "유입 전략 분석 필요"
            }
        }

        return fallback_map.get(agent_id, {"note": "분석 실패"})

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
        """전문 에이전트 결과를 마크다운으로 통합"""
        integrated = "## 전문 에이전트 분석 결과\n\n"
        
        routing = results.get("_routing", {})
        if routing:
            pass # routing info 로깅 (생략)
        
        # 1. Market
        if results.get("market_analysis"):
            integrated += "### 📊 시장 분석 (Market Agent)\n\n"
            integrated += self.agents["market"].format_as_markdown(results["market_analysis"])
            integrated += "\n"
        
        # 2. BM
        if results.get("business_model"):
            integrated += "### 💰 비즈니스 모델 (BM Agent)\n\n"
            integrated += self.agents["bm"].format_as_markdown(results["business_model"])
            integrated += "\n"
            
        # 3. Tech [NEW]
        if results.get("tech_architecture"):
            integrated += "### 🏗️ 기술 아키텍처 (Tech Architect)\n\n"
            # 람다 에이전트의 format 메서드 사용
            integrated += self.agents["tech"].format_as_markdown(results["tech_architecture"])
            integrated += "\n"

        # 4. Content [NEW]
        if results.get("content_strategy"):
            integrated += "### 📣 콘텐츠 전략 (Content Strategist)\n\n"
            integrated += self.agents["content"].format_as_markdown(results["content_strategy"])
            integrated += "\n"
        
        # 5. Financial
        if results.get("financial_plan"):
            integrated += "### 📈 재무 계획 (Financial Agent)\n\n"
            integrated += self.agents["financial"].format_as_markdown(results["financial_plan"])
            integrated += "\n"
        
        # 6. Risk
        if results.get("risk_analysis"):
            integrated += "### ⚠️ 리스크 분석 (Risk Agent)\n\n"
            integrated += self.agents["risk"].format_as_markdown(results["risk_analysis"])
            integrated += "\n"
        
        return integrated

# 하위 호환성을 위해 alias 제공
PlanSupervisor = NativeSupervisor

if __name__ == "__main__":
    supervisor = NativeSupervisor()
