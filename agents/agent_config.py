"""
PlanCraft - Multi-Agent 설정 모듈

에이전트 스펙, 의존성 그래프, 실행 정책을 코드에서 분리하여
유지보수성과 확장성을 향상시킵니다.

[NEW] YAML 외부 설정 지원:
    config/agents.yaml 파일에서 에이전트 설정을 로드합니다.
    코드 수정 없이 에이전트 추가/수정 가능 (OCP 원칙)

사용법:
    from agents.agent_config import AGENT_REGISTRY, get_dependency_graph

    for agent in AGENT_REGISTRY.values():
        print(f"{agent.name}: {agent.description}")
"""

import os
import sys
from typing import Dict, List, Any, Optional, Callable, Type, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

# =============================================================================
# 프로젝트 루트 경로 보장 (Streamlit 환경 호환)
# =============================================================================
# importlib.import_module()이 실행 환경에 관계없이 동작하도록
# 프로젝트 루트를 sys.path에 추가합니다.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# =============================================================================
# Type Checking용 Forward Reference (순환 import 방지)
# =============================================================================
if TYPE_CHECKING:
    from agents.specialists.market_agent import MarketAgent
    from agents.specialists.bm_agent import BMAgent
    from agents.specialists.financial_agent import FinancialAgent
    from agents.specialists.risk_agent import RiskAgent
    from agents.specialists.tech_architect import TechArchitectAgent
    from agents.specialists.content_strategist import ContentStrategistAgent


# =============================================================================
# 에이전트 실행 정책
# =============================================================================

class ExecutionMode(str, Enum):
    """에이전트 실행 모드"""
    REQUIRED = "required"      # 항상 실행
    CONDITIONAL = "conditional"  # LLM 결정에 따라
    OPTIONAL = "optional"      # 사용자가 명시적으로 요청 시만


class ApprovalMode(str, Enum):
    """결과 승인 모드"""
    AUTO = "auto"              # 자동 진행 (승인 불필요)
    REVIEW = "review"          # 사용자 검토 후 진행
    APPROVAL = "approval"      # 명시적 승인 필요


# =============================================================================
# DAG 관련 예외 정의
# =============================================================================

class CyclicDependencyError(Exception):
    """
    DAG에서 순환 의존성이 감지되었을 때 발생하는 예외

    Attributes:
        cycle_agents: 순환에 포함된 에이전트 목록
        message: 상세 에러 메시지

    Example:
        >>> raise CyclicDependencyError(["market", "bm", "market"])
        CyclicDependencyError: 순환 의존성 감지: market → bm → market
    """
    def __init__(self, cycle_agents: List[str], message: str = None):
        self.cycle_agents = cycle_agents
        if message is None:
            cycle_str = " → ".join(cycle_agents)
            message = f"순환 의존성 감지: {cycle_str}"
        self.message = message
        super().__init__(self.message)


class DAGResolutionError(Exception):
    """DAG 해석 중 발생하는 일반 예외"""
    pass


# =============================================================================
# 에이전트 스펙 정의
# =============================================================================

@dataclass
class AgentSpec:
    """
    에이전트 명세

    [리뷰 반영] result_key와 class_path 필드를 추가하여:
    1. Supervisor의 _get_result_key() 하드코딩 제거
    2. 문자열 기반 동적 import 대신 Factory Registry 패턴 지원
    """
    id: str                     # 고유 ID (market, bm, financial, risk)
    name: str                   # UI 표시명
    icon: str                   # 이모지 아이콘
    description: str            # 설명

    # [NEW] 결과 저장 키 (Supervisor에서 results[result_key]로 저장)
    result_key: str = ""        # 예: "market_analysis", "business_model"

    # [NEW] 클래스 경로 (Factory Registry용)
    class_path: str = ""        # 예: "agents.specialists.market_agent.MarketAgent"

    # [NEW] 버전 관리 (future-proof)
    version: str = "1.0.0"      # Semantic versioning (major.minor.patch)
    deprecated: bool = False    # True면 경고 로그 출력, 향후 제거 예정
    deprecated_message: str = ""  # deprecation 안내 메시지

    # 실행 정책
    execution_mode: ExecutionMode = ExecutionMode.CONDITIONAL
    approval_mode: ApprovalMode = ApprovalMode.AUTO

    # 의존성
    depends_on: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)  # 다른 에이전트에게 제공하는 데이터

    # 라우팅 키워드 (LLM 라우팅 시 참조)
    routing_keywords: List[str] = field(default_factory=list)

    # 추가 메타데이터
    timeout_seconds: int = 60
    retry_count: int = 2

    def __post_init__(self):
        """result_key 기본값 자동 설정"""
        if not self.result_key:
            # id 기반 자동 생성: market -> market_analysis
            self.result_key = f"{self.id}_analysis" if self.id != "bm" else "business_model"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "result_key": self.result_key,
            "class_path": self.class_path,
            "version": self.version,
            "deprecated": self.deprecated,
            "execution_mode": self.execution_mode.value,
            "approval_mode": self.approval_mode.value,
            "depends_on": self.depends_on,
            "provides": self.provides,
            "routing_keywords": self.routing_keywords,
        }

    def check_deprecation(self) -> None:
        """deprecated 에이전트 사용 시 경고 로그 출력"""
        if self.deprecated:
            import warnings
            msg = self.deprecated_message or f"Agent '{self.id}' v{self.version} is deprecated and will be removed in a future version."
            warnings.warn(msg, DeprecationWarning, stacklevel=2)


# =============================================================================
# YAML 설정 로딩 (외부 config 지원)
# =============================================================================

def _get_config_path() -> str:
    """config/agents.yaml 경로 반환"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "config", "agents.yaml")


def _load_agents_from_yaml() -> Dict[str, AgentSpec]:
    """
    YAML 파일에서 에이전트 설정 로드

    Returns:
        Dict[str, AgentSpec]: 에이전트 ID -> AgentSpec 매핑

    Note:
        YAML 파일이 없거나 로드 실패 시 빈 딕셔너리 반환 (Fallback으로 하드코딩 사용)
    """
    config_path = _get_config_path()

    if not os.path.exists(config_path):
        return {}

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not config or "agents" not in config:
            return {}

        registry = {}
        for agent_id, agent_data in config["agents"].items():
            spec = AgentSpec(
                id=agent_id,
                name=agent_data.get("name", agent_id),
                icon=agent_data.get("icon", "🤖"),
                description=agent_data.get("description", ""),
                result_key=agent_data.get("result_key", f"{agent_id}_result"),
                class_path=agent_data.get("class_path", ""),
                execution_mode=ExecutionMode(agent_data.get("execution_mode", "conditional")),
                approval_mode=ApprovalMode(agent_data.get("approval_mode", "auto")),
                depends_on=agent_data.get("depends_on", []),
                provides=agent_data.get("provides", []),
                routing_keywords=agent_data.get("routing_keywords", []),
                timeout_seconds=agent_data.get("timeout_seconds", 60),
                retry_count=agent_data.get("retry_count", 2),
            )
            registry[agent_id] = spec

        return registry

    except ImportError:
        # PyYAML 미설치 시 빈 딕셔너리 반환
        return {}
    except Exception as e:
        print(f"[AgentConfig] YAML 로드 실패: {e}")
        return {}


def _load_dependency_reasons_from_yaml() -> Dict[tuple, str]:
    """YAML에서 의존성 이유 매핑 로드"""
    config_path = _get_config_path()

    if not os.path.exists(config_path):
        return {}

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not config or "dependency_reasons" not in config:
            return {}

        reasons = {}
        for key, value in config["dependency_reasons"].items():
            # "market_to_bm" -> ("market", "bm")
            parts = key.split("_to_")
            if len(parts) == 2:
                reasons[(parts[0], parts[1])] = value

        return reasons

    except Exception:
        return {}


def _load_purpose_presets_from_yaml() -> Dict[str, List[str]]:
    """YAML에서 목적별 에이전트 프리셋 로드"""
    config_path = _get_config_path()

    if not os.path.exists(config_path):
        return {}

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        return config.get("purpose_presets", {})

    except Exception:
        return {}


# =============================================================================
# 에이전트 레지스트리 (YAML 우선, Fallback으로 하드코딩)
# =============================================================================

# 먼저 YAML에서 로드 시도
_YAML_REGISTRY = _load_agents_from_yaml()
_YAML_DEPENDENCY_REASONS = _load_dependency_reasons_from_yaml()
_YAML_PURPOSE_PRESETS = _load_purpose_presets_from_yaml()

# YAML 로드 성공 시 사용, 실패 시 하드코딩 Fallback
if _YAML_REGISTRY:
    AGENT_REGISTRY: Dict[str, AgentSpec] = _YAML_REGISTRY
else:
    # Fallback: 하드코딩된 레지스트리 (YAML 미사용 환경 호환)
    AGENT_REGISTRY: Dict[str, AgentSpec] = {
        "market": AgentSpec(
            id="market",
            name="시장 분석",
            icon="📊",
            description="TAM/SAM/SOM 3단계 시장 규모 분석, 경쟁사 실명 분석, 트렌드 파악",
            result_key="market_analysis",
            class_path="agents.specialists.market_agent.MarketAgent",
            execution_mode=ExecutionMode.CONDITIONAL,
            approval_mode=ApprovalMode.AUTO,
            depends_on=[],
            provides=["tam", "sam", "som", "competitors", "trends"],
        routing_keywords=["시장", "규모", "경쟁사", "트렌드", "TAM", "SAM", "SOM", "분석"],
        timeout_seconds=90,
    ),

    "bm": AgentSpec(
        id="bm",
        name="비즈니스 모델",
        icon="💰",
        description="수익 모델 다각화, 가격 전략 수립, B2B/B2C 계층 설계",
        result_key="business_model",  # [NEW]
        class_path="agents.specialists.bm_agent.BMAgent",  # [NEW]
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=["market"],  # 시장 분석 후 BM 수립 (순서 보장)
        provides=["revenue_model", "pricing", "moat"],
        routing_keywords=["수익", "가격", "BM", "비즈니스", "모델", "구독", "광고", "B2B", "B2C"],
        timeout_seconds=60,
    ),

    "financial": AgentSpec(
        id="financial",
        name="재무 계획",
        icon="📈",
        description="초기 투자비 산출, 월별 손익 시뮬레이션, BEP 계산, 3시나리오 분석",
        result_key="financial_plan",  # [NEW]
        class_path="agents.specialists.financial_agent.FinancialAgent",  # [NEW]
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=["bm"],  # BM 결과 필수
        provides=["investment", "monthly_pl", "bep", "scenarios"],
        routing_keywords=["재무", "투자", "비용", "매출", "BEP", "손익", "예산", "자금"],
        timeout_seconds=90,
    ),

    "risk": AgentSpec(
        id="risk",
        name="리스크 분석",
        icon="⚠️",
        description="8가지 리스크 카테고리 분석, 위험 점수 정량화, 대응 전략 수립",
        result_key="risk_analysis",  # [NEW]
        class_path="agents.specialists.risk_agent.RiskAgent",  # [NEW]
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=["bm"],  # BM 결과 참조
        provides=["risks", "mitigation", "kri"],
        routing_keywords=["리스크", "위험", "대응", "문제", "장애", "규제"],
        timeout_seconds=60,
    ),

    "tech": AgentSpec(
        id="tech",
        name="기술 설계",
        icon="🏗️",
        description="기술 스택 선정, 시스템 아키텍처 설계, 개발 로드맵 수립",
        result_key="tech_architecture",  # [NEW]
        class_path="agents.specialists.tech_architect.TechArchitectAgent",  # [NEW]
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=[],  # 독립적으로 수행 가능
        provides=["recommended_stack", "architecture_desc", "roadmap"],
        routing_keywords=["기술", "아키텍처", "개발", "스택", "인프라", "클라우드", "앱", "웹"],
        timeout_seconds=60,
    ),

    "content": AgentSpec(
        id="content",
        name="콘텐츠 전략",
        icon="📣",
        description="브랜딩 컨셉, 핵심 메시지, 초기 사용자 유입 전략 수립",
        result_key="content_strategy",  # [NEW]
        class_path="agents.specialists.content_strategist.ContentStrategistAgent",  # [NEW]
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=["market"],  # 시장 분석(타겟) 필요
        provides=["brand_concept", "acquisition_strategy"],
        routing_keywords=["마케팅", "브랜딩", "콘텐츠", "홍보", "유입", "운영"],
        timeout_seconds=60,
    ),
}


# =============================================================================
# 실행 계획 (Execution Plan) - Plan-and-Execute 패턴
# =============================================================================

@dataclass
class ExecutionStep:
    """실행 계획의 한 단계 (병렬 실행 가능한 에이전트 그룹)"""
    step_id: int
    agent_ids: List[str]  # 병렬 실행할 에이전트 ID 목록
    description: str = "" # 단계 설명

@dataclass
class ExecutionPlan:
    """전체 실행 계획"""
    steps: List[ExecutionStep]
    reasoning: str        # 계획 수립 근거
    total_estimated_time: int = 0
    human_readable_description: str = ""  # [NEW] 사용자 친화적 실행 설명
    
    def get_all_agents(self) -> List[str]:
        """모든 참여 에이전트 ID 반환"""
        return [agent_id for step in self.steps for agent_id in step.agent_ids]


# =============================================================================
# 의존성 그래프 유틸리티 (DAG)
# =============================================================================

def get_dependency_graph() -> Dict[str, List[str]]:
    """의존성 그래프 반환 (에이전트ID -> 의존하는 에이전트ID 목록)"""
    return {
        agent_id: spec.depends_on
        for agent_id, spec in AGENT_REGISTRY.items()
    }


def _get_dependency_reason(from_agent: str, to_agent: str) -> str:
    """
    에이전트 간 의존 이유 반환 (Plan step description에 의존 이유 명시)

    Args:
        from_agent: 선행 에이전트 (데이터 제공)
        to_agent: 후행 에이전트 (데이터 소비)

    Returns:
        str: 의존 이유 설명

    Example:
        >>> _get_dependency_reason("market", "bm")
        "시장 데이터 기반"
    """
    # YAML에서 로드한 값 우선 사용
    if _YAML_DEPENDENCY_REASONS:
        result = _YAML_DEPENDENCY_REASONS.get((from_agent, to_agent))
        if result:
            return result

    # Fallback: 하드코딩된 매핑
    dependency_reasons = {
        ("market", "bm"): "시장 데이터 기반",
        ("market", "content"): "타겟 정보 참조",
        ("bm", "financial"): "수익 모델 반영",
        ("bm", "risk"): "BM 리스크 분석",
    }

    return dependency_reasons.get((from_agent, to_agent), "참조")


def _detect_cycle_path(
    remaining: set,
    graph: Dict[str, List[str]]
) -> List[str]:
    """
    DFS를 사용하여 순환 경로를 탐지합니다.

    Args:
        remaining: 아직 처리되지 않은 에이전트 집합
        graph: 의존성 그래프 (agent -> [dependencies])

    Returns:
        List[str]: 순환 경로 (예: ["A", "B", "C", "A"])
                   순환이 없으면 빈 리스트 반환

    Algorithm:
        - 3-color DFS (WHITE: 미방문, GRAY: 처리중, BLACK: 완료)
        - GRAY 노드를 다시 만나면 순환 존재

    Example:
        >>> graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        >>> _detect_cycle_path({"A", "B", "C"}, graph)
        ["A", "B", "C", "A"]
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in remaining}
    parent = {node: None for node in remaining}
    cycle_path = []

    def dfs(node: str) -> bool:
        """Returns True if cycle detected"""
        color[node] = GRAY

        for neighbor in graph.get(node, []):
            if neighbor not in remaining:
                continue

            if color[neighbor] == GRAY:
                # 순환 발견! 경로 재구성
                cycle_path.append(neighbor)
                current = node
                while current != neighbor:
                    cycle_path.append(current)
                    current = parent.get(current)
                    if current is None:
                        break
                cycle_path.append(neighbor)
                cycle_path.reverse()
                return True

            if color[neighbor] == WHITE:
                parent[neighbor] = node
                if dfs(neighbor):
                    return True

        color[node] = BLACK
        return False

    for node in remaining:
        if color[node] == WHITE:
            if dfs(node):
                return cycle_path

    return cycle_path


def resolve_execution_plan_dag(required_agents: List[str], reasoning: str = "") -> ExecutionPlan:
    """
    DAG 기반 병렬 실행 계획 생성 (Topological Sort with Grouping)
    
    Returns:
        ExecutionPlan: 단계별로 병렬 실행 가능한 에이전트 그룹이 정의된 계획
    """
    if not required_agents:
        return ExecutionPlan(steps=[], reasoning=reasoning)
    
    graph = get_dependency_graph()
    
    # 1. 누락된 의존성 추가 (Closure)
    all_required = set(required_agents)
    while True:
        added = False
        current_list = list(all_required)
        for agent_id in current_list:
            for dep in graph.get(agent_id, []):
                if dep not in all_required:
                    all_required.add(dep)
                    added = True
        if not added:
            break
            
    # 2. 진입 차수(Indegree) 계산
    # subset에 대해서만 그래프 구축
    subset_graph = {a: [d for d in graph.get(a, []) if d in all_required] for a in all_required}
    in_degree = {a: 0 for a in all_required}
    
    for agent, deps in subset_graph.items():
        # deps는 'agent'가 의존하는 대상들.
        # 즉 deps -> agent 방향. 따라서 의존성이 있으면 내 indegree가 증가하지 않음?
        # 아니, 의존성 A->B (B가 A에 의존)라면 A가 끝나야 B 시작.
        # 여기선 depends_on이 [A]면 A가 선행되어야 함.
        pass

    # Kahn's Algorithm 변형 (Layer별 그룹핑)
    # 1. depends_on에 있는 에이전트들이 완료되었는지를 체크
    
    layers = []
    remaining = set(all_required)
    completed = set()
    
    while remaining:
        # 현재 완료된(또는 의존성 없는) 에이전트들에만 의존하는 에이전트들 찾기
        # 즉, 자신의 모든 의존성이 completed 집합에 있는 경우
        layer = []
        for agent in remaining:
            dependencies = subset_graph.get(agent, [])
            if all(dep in completed for dep in dependencies):
                layer.append(agent)
        
        if not layer:
            # =====================================================================
            # 순환 의존성 감지 - 명시적 처리
            # =====================================================================
            # Kahn's Algorithm에서 layer가 비어있으면 순환 의존성 존재

            # 1. 순환 경로 탐지 (DFS)
            cycle_path = _detect_cycle_path(remaining, subset_graph)

            # 2. 로깅 (운영 환경에서 모니터링 가능)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[DAG] 순환 의존성 감지! "
                f"영향 에이전트: {list(remaining)}, "
                f"순환 경로: {cycle_path}"
            )

            # 3. Fallback 처리: 순환 그룹을 우선순위 기반 순차 실행
            # (프로덕션에서는 CyclicDependencyError 발생 권장)
            # raise CyclicDependencyError(cycle_path)

            # Fallback: 우선순위 순으로 강제 실행 (데이터 손실 최소화)
            priority_fallback = ["market", "tech", "bm", "content", "financial", "risk"]
            layer = sorted(
                list(remaining),
                key=lambda x: priority_fallback.index(x) if x in priority_fallback else 99
            )
            logger.warning(f"[DAG] Fallback 적용: {layer} 순차 실행")
        
        # 이름순/우선순위 정렬 (결정적 순서 보장)
        priority_list = ["market", "tech", "bm", "content", "financial", "risk"]
        priority_map = {name: i for i, name in enumerate(priority_list)}
        
        layer.sort(key=lambda x: priority_map.get(x, 99))
        
        layers.append(layer)
        
        # 상태 업데이트
        for agent in layer:
            remaining.remove(agent)
            completed.add(agent)

    # Create Steps
    execution_steps = []
    total_time = 0

    descriptions = []

    for i, layer in enumerate(layers):
        step_agents = layer

        # Priority sort within layer
        step_agents.sort(key=lambda x: priority_map.get(x, 999))

        # Calculate time (max of agents in parallel)
        step_time = max([AGENT_REGISTRY[a].timeout_seconds for a in step_agents]) if step_agents else 0
        total_time += step_time

        # [ENHANCED] Step description에 의존 이유 포함
        agent_names = [AGENT_REGISTRY[a].name for a in step_agents]

        # 각 에이전트의 의존 이유 수집
        dep_reasons = []
        for agent_id in step_agents:
            deps = subset_graph.get(agent_id, [])
            for dep in deps:
                reason = _get_dependency_reason(dep, agent_id)
                dep_spec = AGENT_REGISTRY.get(dep)
                agent_spec = AGENT_REGISTRY.get(agent_id)
                if dep_spec and agent_spec:
                    dep_reasons.append(f"{dep_spec.name} → {agent_spec.name} ({reason})")

        # Step description 생성
        if dep_reasons:
            desc = f"단계 {i+1}: {', '.join(agent_names)} 병렬 실행 [{'; '.join(dep_reasons)}]"
        else:
            desc = f"단계 {i+1}: {', '.join(agent_names)} 병렬 실행 [독립 실행 가능]"

        execution_steps.append(ExecutionStep(step_id=i+1, agent_ids=step_agents, description=desc))

        # Human readable description part (의존 이유 포함)
        if i == 0:
            descriptions.append(f"먼저 {', '.join(agent_names)}을(를) 통해 기반 분석을 수행합니다.")
        else:
            # 의존 관계 설명 추가
            if dep_reasons:
                dep_summary = ", ".join([r.split(" (")[1].rstrip(")") for r in dep_reasons[:2]])
                descriptions.append(
                    f"그 다음, {dep_summary} 데이터를 바탕으로 {', '.join(agent_names)}을(를) 진행합니다."
                )
            else:
                descriptions.append(f"그 다음, {', '.join(agent_names)}을(를) 진행합니다.")

    human_readable = " ".join(descriptions)

    return ExecutionPlan(
        steps=execution_steps, 
        reasoning=reasoning, 
        total_estimated_time=total_time,
        human_readable_description=human_readable
    )


def resolve_execution_order(required_agents: List[str]) -> List[str]:
    """
    (구버전 호환용) 단순 순차 리스트 반환
    ExecutionPlan을 생성하고 플랫하게 펼침
    """
    plan = resolve_execution_plan_dag(required_agents)
    flat_order = []
    for step in plan.steps:
        flat_order.extend(step.agent_ids)
    return flat_order


# =============================================================================
# DAG → Mermaid 그래프 Export (디버깅/문서화용)
# =============================================================================

def export_plan_to_mermaid(plan: ExecutionPlan, title: str = "Execution Plan") -> str:
    """
    실행 계획을 Mermaid 다이어그램 코드로 변환

    디버깅, 문서화, UI 시각화에 활용 가능.

    Args:
        plan: 실행 계획 (ExecutionPlan)
        title: 다이어그램 제목

    Returns:
        str: Mermaid flowchart 코드

    Example:
        >>> plan = resolve_execution_plan_dag(["market", "bm", "financial"])
        >>> mermaid_code = export_plan_to_mermaid(plan)
        >>> print(mermaid_code)
        ```mermaid
        flowchart TD
            subgraph Step1["단계 1: 시장 분석"]
                market["📊 시장 분석"]
            end
            subgraph Step2["단계 2: 비즈니스 모델"]
                bm["💰 비즈니스 모델"]
            end
            Step1 --> Step2
        ```
    """
    lines = ["```mermaid", f"flowchart TD", f"    %% {title}"]

    # 각 단계를 subgraph로 표현
    for step in plan.steps:
        step_id = f"Step{step.step_id}"
        agent_names = [AGENT_REGISTRY[a].name for a in step.agent_ids if a in AGENT_REGISTRY]
        step_label = f"단계 {step.step_id}: {', '.join(agent_names)}"

        lines.append(f"    subgraph {step_id}[\"{step_label}\"]")

        for agent_id in step.agent_ids:
            spec = AGENT_REGISTRY.get(agent_id)
            if spec:
                lines.append(f"        {agent_id}[\"{spec.icon} {spec.name}\"]")

        lines.append("    end")

    # 단계 간 연결 (순차적)
    for i in range(len(plan.steps) - 1):
        lines.append(f"    Step{plan.steps[i].step_id} --> Step{plan.steps[i+1].step_id}")

    # 의존성 관계 표시 (점선)
    dep_graph = get_dependency_graph()
    for agent_id, deps in dep_graph.items():
        if agent_id in plan.get_all_agents():
            for dep in deps:
                if dep in plan.get_all_agents():
                    lines.append(f"    {dep} -.->|의존| {agent_id}")

    lines.append("```")

    return "\n".join(lines)


def export_dag_to_mermaid(required_agents: List[str] = None) -> str:
    """
    에이전트 의존성 그래프를 Mermaid 코드로 변환

    Args:
        required_agents: 포함할 에이전트 목록 (None이면 전체)

    Returns:
        str: Mermaid flowchart 코드

    Example:
        >>> print(export_dag_to_mermaid(["market", "bm", "financial", "risk"]))
        ```mermaid
        flowchart LR
            market["📊 시장 분석"]
            bm["💰 비즈니스 모델"]
            market --> bm
            bm --> financial
            bm --> risk
        ```
    """
    agents = required_agents or list(AGENT_REGISTRY.keys())
    dep_graph = get_dependency_graph()

    lines = ["```mermaid", "flowchart LR"]

    # 노드 정의
    for agent_id in agents:
        spec = AGENT_REGISTRY.get(agent_id)
        if spec:
            lines.append(f"    {agent_id}[\"{spec.icon} {spec.name}\"]")

    lines.append("")

    # 의존성 엣지
    for agent_id in agents:
        for dep in dep_graph.get(agent_id, []):
            if dep in agents:
                # 의존 이유 추가
                dep_reason = _get_dependency_reason(dep, agent_id)
                lines.append(f"    {dep} -->|{dep_reason}| {agent_id}")

    lines.append("```")

    return "\n".join(lines)


def get_agents_for_purpose(purpose: str) -> List[str]:
    """
    목적에 따른 권장 에이전트 목록 반환

    Args:
        purpose: 분석 목적 (기획서/투자유치/아이디어검증 등)
    """
    # YAML에서 로드한 프리셋 우선 사용
    if _YAML_PURPOSE_PRESETS:
        for preset_key, agents in _YAML_PURPOSE_PRESETS.items():
            if preset_key in purpose:
                return agents

    # Fallback: 하드코딩된 매핑
    purpose_lower = purpose.lower()

    if "투자" in purpose_lower:
        return ["market", "bm", "financial", "risk"]
    elif "아이디어" in purpose_lower or "검증" in purpose_lower:
        return ["market", "bm"]
    elif "기획서" in purpose_lower:
        return ["market", "bm", "financial", "risk"]
    else:
        # 기본값: 모두
        return list(AGENT_REGISTRY.keys())


def get_routing_prompt() -> str:
    """LLM 라우팅용 에이전트 설명 프롬프트 생성"""
    lines = ["## 사용 가능한 전문 에이전트", ""]
    
    for agent_id, spec in AGENT_REGISTRY.items():
        lines.append(f"### {spec.icon} {spec.name} (`{agent_id}`)")
        lines.append(f"- **설명**: {spec.description}")
        lines.append(f"- **키워드**: {', '.join(spec.routing_keywords)}")
        if spec.depends_on:
            lines.append(f"- **의존성**: {', '.join(spec.depends_on)}")
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# 에이전트 등록 API (런타임 확장용)
# =============================================================================

def register_agent(spec: AgentSpec) -> None:
    """새 에이전트 등록 (런타임)"""
    AGENT_REGISTRY[spec.id] = spec


def unregister_agent(agent_id: str) -> bool:
    """에이전트 등록 해제"""
    if agent_id in AGENT_REGISTRY:
        del AGENT_REGISTRY[agent_id]
        return True
    return False


def get_agent_spec(agent_id: str) -> Optional[AgentSpec]:
    """에이전트 스펙 조회"""
    return AGENT_REGISTRY.get(agent_id)


def get_result_key(agent_id: str) -> str:
    """
    [NEW] 에이전트 ID → 결과 키 매핑 (Registry 기반)

    Supervisor의 하드코딩된 _get_result_key()를 대체합니다.

    Returns:
        str: 결과 저장 키 (예: "market_analysis", "business_model")
    """
    spec = AGENT_REGISTRY.get(agent_id)
    if spec:
        return spec.result_key
    return f"{agent_id}_result"  # Fallback


# =============================================================================
# Agent Factory Registry (클래스 기반 동적 생성)
# =============================================================================

# [캐시] 동적 import 결과 저장 (성능 최적화)
_AGENT_CLASS_CACHE: Dict[str, Type] = {}


def get_agent_class(agent_id: str) -> Optional[Type]:
    """
    [NEW] Factory Pattern: 에이전트 ID → 클래스 객체 반환

    문자열 기반 동적 import를 캡슐화하여:
    1. Supervisor에서 하드코딩된 class_path 제거
    2. 타입 안정성 및 IDE 자동완성 지원
    3. 캐싱을 통한 반복 import 방지

    Returns:
        Type: 에이전트 클래스 (예: MarketAgent, BMAgent)
        None: 등록되지 않은 에이전트

    Example:
        >>> AgentClass = get_agent_class("market")
        >>> agent = AgentClass(llm=my_llm)
        >>> result = agent.run(service_overview="...")
    """
    # 캐시 확인
    if agent_id in _AGENT_CLASS_CACHE:
        return _AGENT_CLASS_CACHE[agent_id]

    spec = AGENT_REGISTRY.get(agent_id)
    if not spec or not spec.class_path:
        return None

    try:
        import importlib
        module_path, class_name = spec.class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        agent_class = getattr(module, class_name)

        # 캐시에 저장
        _AGENT_CLASS_CACHE[agent_id] = agent_class
        return agent_class

    except (ImportError, AttributeError) as e:
        # Import 실패 시 로깅 (순환 import 방지를 위해 여기서만 import)
        try:
            from utils.file_logger import get_file_logger
            get_file_logger().error(f"[AgentFactory] {agent_id} 로드 실패: {e}")
        except ImportError:
            pass
        return None


def create_agent(agent_id: str, llm=None) -> Optional[Any]:
    """
    [NEW] Factory Pattern: 에이전트 인스턴스 생성

    Args:
        agent_id: 에이전트 ID (market, bm, financial, risk, tech, content)
        llm: LLM 인스턴스 (None이면 기본 LLM 사용)

    Returns:
        에이전트 인스턴스 또는 None
    """
    agent_class = get_agent_class(agent_id)
    if agent_class is None:
        return None

    try:
        return agent_class(llm=llm)
    except Exception as e:
        try:
            from utils.file_logger import get_file_logger
            get_file_logger().error(f"[AgentFactory] {agent_id} 인스턴스 생성 실패: {e}")
        except ImportError:
            pass
        return None


# =============================================================================
# Tool-based Agent Wrapper (LangGraph Best Practice)
# =============================================================================
#
# create_react_agent와 함께 사용 가능한 Tool 래핑 패턴
# Supervisor가 에이전트를 Tool로 호출하여 더 유연한 오케스트레이션 가능
#
# 사용 예시:
#     tools = [create_agent_tool("market"), create_agent_tool("bm")]
#     supervisor = create_react_agent(llm, tools, system_prompt)
# =============================================================================

def create_agent_tool(agent_id: str, llm=None):
    """
    에이전트를 LangChain Tool로 래핑

    LangGraph create_react_agent 패턴에서 사용 가능한 Tool 생성.
    Supervisor가 동적으로 에이전트를 호출할 때 사용.

    Args:
        agent_id: 에이전트 ID
        llm: LLM 인스턴스 (선택)

    Returns:
        langchain_core.tools.StructuredTool: 에이전트를 래핑한 Tool

    Example:
        >>> from langgraph.prebuilt import create_react_agent
        >>> tools = [create_agent_tool("market"), create_agent_tool("bm")]
        >>> agent = create_react_agent(llm, tools)
        >>> agent.invoke({"messages": [HumanMessage(content="...")]})
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field as PydanticField

    spec = AGENT_REGISTRY.get(agent_id)
    if not spec:
        raise ValueError(f"Unknown agent_id: {agent_id}")

    # 에이전트 인스턴스 생성 (캐싱)
    agent = create_agent(agent_id, llm=llm)
    if agent is None:
        raise RuntimeError(f"Failed to create agent: {agent_id}")

    # 동적 입력 스키마 생성
    class AgentInput(BaseModel):
        """에이전트 실행 입력"""
        service_overview: str = PydanticField(description="서비스 개요")
        target_market: str = PydanticField(default="", description="타겟 시장 (선택)")
        target_users: str = PydanticField(default="", description="타겟 사용자 (선택)")

    def run_agent(service_overview: str, target_market: str = "", target_users: str = "") -> str:
        """에이전트 실행 및 마크다운 변환"""
        try:
            # 에이전트별 필요한 파라미터 전달
            kwargs = {"service_overview": service_overview}

            if agent_id == "market":
                kwargs["target_market"] = target_market
            elif agent_id in ["bm", "content", "tech"]:
                kwargs["target_users"] = target_users

            result = agent.run(**kwargs)

            # 마크다운 형식으로 변환
            if hasattr(agent, "format_as_markdown"):
                return agent.format_as_markdown(result)
            return str(result)

        except Exception as e:
            return f"[ERROR] {agent_id} 실행 실패: {e}"

    return StructuredTool.from_function(
        func=run_agent,
        name=f"analyze_{agent_id}",
        description=f"{spec.icon} {spec.name}: {spec.description}",
        args_schema=AgentInput,
    )


def create_all_agent_tools(llm=None) -> List:
    """
    모든 등록된 에이전트를 Tool 목록으로 생성

    create_react_agent에서 사용할 Tool 목록 반환.

    Returns:
        List[StructuredTool]: 에이전트 Tool 목록

    Example:
        >>> from langgraph.prebuilt import create_react_agent
        >>> tools = create_all_agent_tools(llm)
        >>> supervisor = create_react_agent(llm, tools, supervisor_prompt)
    """
    tools = []
    for agent_id in AGENT_REGISTRY.keys():
        try:
            tool = create_agent_tool(agent_id, llm=llm)
            tools.append(tool)
        except Exception as e:
            # 로깅만 하고 계속 진행
            try:
                from utils.file_logger import get_file_logger
                get_file_logger().warning(f"[ToolFactory] {agent_id} Tool 생성 스킵: {e}")
            except ImportError:
                pass
    return tools


# =============================================================================
# 승인 정책 유틸리티
# =============================================================================

def requires_approval(agent_id: str) -> bool:
    """에이전트 결과가 사용자 승인을 필요로 하는지 확인"""
    spec = AGENT_REGISTRY.get(agent_id)
    if not spec:
        return False
    return spec.approval_mode in [ApprovalMode.APPROVAL, ApprovalMode.REVIEW]


def set_approval_mode(agent_id: str, mode: ApprovalMode) -> bool:
    """에이전트 승인 모드 변경"""
    spec = AGENT_REGISTRY.get(agent_id)
    if spec:
        spec.approval_mode = mode
        return True
    return False


# =============================================================================
# 디버깅/관리 유틸리티
# =============================================================================

def print_agent_summary():
    """에이전트 요약 출력 (디버깅용)"""
    print("=" * 60)
    print("PlanCraft Agent Registry")
    print("=" * 60)
    
    for agent_id, spec in AGENT_REGISTRY.items():
        deps = f" (deps: {spec.depends_on})" if spec.depends_on else ""
        print(f"{spec.icon} {spec.name} [{agent_id}]{deps}")
    
    print("=" * 60)
    print(f"Execution Order (all): {resolve_execution_order(list(AGENT_REGISTRY.keys()))}")


if __name__ == "__main__":
    print_agent_summary()
    print("\n" + get_routing_prompt())
