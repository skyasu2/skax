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
    ↓       ↓       ↓       ↓
  Market   BM   Financial  Risk
    ↓       ↓       ↓       ↓
    └───────┴───┬───┴───────┘
                ↓
    Result Integration
        ↓
    Writer Context
"""

from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.llm import get_llm
from utils.file_logger import FileLogger
from agents.specialist_tools import (
    get_specialist_tools,
    get_tool_descriptions_for_llm,
    analyze_market,
    analyze_business_model,
    analyze_financials,
    analyze_risks,
)

logger = FileLogger()


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
    
    ROUTER_SYSTEM_PROMPT = """당신은 기획서 분석 작업을 조율하는 Supervisor입니다.

사용자의 서비스 아이디어를 분석하여, 어떤 전문 분석이 필요한지 결정하세요.

## 사용 가능한 분석 유형

1. **market**: 시장 분석 (TAM/SAM/SOM, 경쟁사) -- 필수
2. **bm**: 비즈니스 모델 (수익화, 가격 전략) -- 필수
3. **tech**: 기술 아키텍처 (스택, 로드맵)
   - 필요 시점: 앱/웹 개발, 플랫폼 구축, 특정 기술(AI, 블록체인 등) 언급 시
4. **content**: 콘텐츠/브랜딩 전략 (마케팅, 홍보)
   - 필요 시점: 커뮤니티, SNS, 플랫폼 활성화, 마케팅 전략 필요 시
5. **financial**: 재무 계획 (비용/매출 예측)
   - 필요 시점: 사업성 검토, 투자 유치, 구체적 예산 산정 필요 시
6. **risk**: 리스크 분석 (규제, 기술 난관)
   - 필요 시점: 법적 이슈 가능성, 기술적 불확실성이 높을 때

## 판단 기준

1. **Market/BM은 기본**: 대부분의 기획서에 `market`, `bm`은 필수입니다.
2. **목적별 추가**:
   - **IT 개발**: + `tech`
   - **플랫폼/서비스**: + `content`
   - **사업계획서**: + `financial`, `risk`
3. **의존성**: `tech`는 독립적이지만, `content`는 `market`(타겟)이 필요합니다.

## 출력 예시
- 일반 앱 기획: ["market", "bm", "tech"]
- 커뮤니티 기획: ["market", "bm", "content"]
- 투자용 사업계획: ["market", "bm", "financial", "risk", "tech"]
"""

    def __init__(self, llm=None):
        self.llm = llm or get_llm(temperature=0.3)
        self.router_llm = self.llm.with_structured_output(RoutingDecision)
        
        # [NEW] Config 기반 에이전트 로드
        from agents.agent_config import (
            AGENT_REGISTRY,
            get_routing_prompt,
            resolve_execution_order,
        )
        self.agent_registry = AGENT_REGISTRY
        self.routing_prompt = get_routing_prompt()
        
        # 전문 에이전트 동적 초기화
        self.agents = {}
        self._init_agents()
        
        logger.info(f"[NativeSupervisor] 초기화 완료 (에이전트 {len(self.agents)}개)")
    
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


class NativeSupervisor:
    # ... (ROUTER_SYSTEM_PROMPT는 이미 수정됨) ...
    
    # ... (__init__ 생략) ...

    def _init_agents(self):
        """Config 기반 에이전트 초기화"""
        # 1. 클래스 기반 에이전트 매핑
        agent_classes = {
            "market": "agents.specialists.market_agent.MarketAgent",
            "bm": "agents.specialists.bm_agent.BMAgent",
            "financial": "agents.specialists.financial_agent.FinancialAgent",
            "risk": "agents.specialists.risk_agent.RiskAgent",
        }
        
        # 2. 함수 기반 에이전트 매핑 [NEW]
        function_agents = {
            "tech": "agents.specialists.tech_architect.run_tech_architect",
            "content": "agents.specialists.content_strategist.run_content_strategist"
        }
        
        import importlib

        # 클래스 에이전트 로드
        for agent_id, class_path in agent_classes.items():
            try:
                module_path, class_name = class_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                agent_class = getattr(module, class_name)
                self.agents[agent_id] = agent_class(llm=self.llm)
                logger.info(f"  - [Class] {agent_id} 초기화 완료")
            except Exception as e:
                logger.error(f"  - [Class] {agent_id} 초기화 실패: {e}")

        # 함수 에이전트 로드
        for agent_id, func_path in function_agents.items():
            try:
                module_path, func_name = func_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                run_func = getattr(module, func_name)
                self.agents[agent_id] = LambdaAgent(run_func)
                logger.info(f"  - [Func] {agent_id} 초기화 완료")
            except Exception as e:
                logger.error(f"  - [Func] {agent_id} 초기화 실패: {e}")

    
    def decide_required_agents(
        self,
        service_overview: str,
        purpose: str = "기획서 작성"
    ) -> RoutingDecision:
        """
        동적 라우팅: 필요한 에이전트 결정
        
        Args:
            service_overview: 서비스 개요
            purpose: 분석 목적
            
        Returns:
            RoutingDecision: 필요한 분석 목록
        """
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
        """
        전문 에이전트 실행 (Plan-and-Execute DAG)
        """
        logger.info("=" * 60)
        logger.info("[NativeSupervisor] 전문 에이전트 오케스트레이션 시작 (DAG)")
        # ... (로그 생략) ...
        
        results = {}
        
        # 1. 동적 라우팅 -> Execution Plan 생성
        # ... (라우팅 로직 그대로) ...
        
        if force_all:
            required = ["market", "bm", "financial", "risk"]
            reasoning = "강제 전체 분석"
        else:
            decision = self.decide_required_agents(service_overview, purpose)
            required = decision.required_analyses
            reasoning = decision.reasoning
        
        # DAG 기반 실행 계획 수립
        from agents.agent_config import resolve_execution_plan_dag
        execution_plan = resolve_execution_plan_dag(required, reasoning)
        
        results["_plan"] = execution_plan
        # ... (로그 생략) ...
        
        # 2. 단계별 병렬 실행
        self._execute_plan(execution_plan, results, {
            "service_overview": service_overview,
            "target_market": target_market,
            "target_users": target_users,
            "tech_stack": tech_stack,
            "development_scope": development_scope,
            "web_search_results": web_search_results,
            "user_constraints": user_constraints or []  # [NEW] 전달
        })
        
        # 3. 결과 통합
        results["integrated_context"] = self._integrate_results(results)
        
        logger.info("[NativeSupervisor] 오케스트레이션 완료")
        return results

    def _execute_plan(self, plan, results: Dict, context: Dict):
        """실행 계획에 따라 단계별 병렬 실행"""
        
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
                        # 결과 키 매핑 (Legacy 호환)
                        result_key = self._get_result_key(agent_id)
                        results[result_key] = result
                        logger.info(f"  ✅ [Done] {agent_id}")
                    except Exception as e:
                        logger.error(f"  ❌ [Error] {agent_id}: {e}")
                        results[self._get_result_key(agent_id)] = {"error": str(e)}

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

    def _get_result_key(self, agent_id: str) -> str:
        """에이전트 ID -> 결과 키 매핑"""
        mapping = {
            "market": "market_analysis",
            "bm": "business_model",
            "financial": "financial_plan",
            "risk": "risk_analysis",
            "tech": "tech_architecture",    # [NEW]
            "content": "content_strategy"   # [NEW]
        }
        return mapping.get(agent_id, f"{agent_id}_result")
        
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


# =============================================================================
# 기존 PlanSupervisor 대체
# =============================================================================

# 하위 호환성을 위해 alias 제공
PlanSupervisor = NativeSupervisor


# =============================================================================
# 단독 실행 테스트
# =============================================================================

if __name__ == "__main__":
    supervisor = NativeSupervisor()
    
    # 동적 라우팅 테스트
    decision = supervisor.decide_required_agents(
        service_overview="위치 기반 소셜 러닝 앱",
        purpose="투자 유치용 기획서"
    )
    print(f"필요한 분석: {decision.required_analyses}")
    print(f"이유: {decision.reasoning}")
