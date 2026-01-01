"""
PlanCraft - Multi-Agent 설정 모듈

에이전트 스펙, 의존성 그래프, 실행 정책을 코드에서 분리하여
유지보수성과 확장성을 향상시킵니다.

사용법:
    from agents.agent_config import AGENT_REGISTRY, get_dependency_graph
    
    for agent in AGENT_REGISTRY.values():
        print(f"{agent.name}: {agent.description}")
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


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
# 에이전트 스펙 정의
# =============================================================================

@dataclass
class AgentSpec:
    """에이전트 명세"""
    id: str                     # 고유 ID (market, bm, financial, risk)
    name: str                   # UI 표시명
    icon: str                   # 이모지 아이콘
    description: str            # 설명
    
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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "execution_mode": self.execution_mode.value,
            "approval_mode": self.approval_mode.value,
            "depends_on": self.depends_on,
            "provides": self.provides,
            "routing_keywords": self.routing_keywords,
        }


# =============================================================================
# 에이전트 레지스트리 (핵심 설정)
# =============================================================================

AGENT_REGISTRY: Dict[str, AgentSpec] = {
    "market": AgentSpec(
        id="market",
        name="시장 분석",
        icon="📊",
        description="TAM/SAM/SOM 3단계 시장 규모 분석, 경쟁사 실명 분석, 트렌드 파악",
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
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=["bm"],  # BM 결과 참조
        provides=["risks", "mitigation", "kri"],
        routing_keywords=["리스크", "위험", "대응", "문제", "장애", "규제"],
        timeout_seconds=60,
    ),
    
    # [NEW] 기술 아키텍트
    "tech": AgentSpec(
        id="tech",
        name="기술 설계",
        icon="🏗️",
        description="기술 스택 선정, 시스템 아키텍처 설계, 개발 로드맵 수립",
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=[], # 독립적으로 수행 가능
        provides=["recommended_stack", "architecture_desc", "roadmap"],
        routing_keywords=["기술", "아키텍처", "개발", "스택", "인프라", "클라우드", "앱", "웹"],
        timeout_seconds=60,
    ),

    # [NEW] 콘텐츠 전략가
    "content": AgentSpec(
        id="content",
        name="콘텐츠 전략",
        icon="📣",
        description="브랜딩 컨셉, 핵심 메시지, 초기 사용자 유입 전략 수립",
        execution_mode=ExecutionMode.CONDITIONAL,
        approval_mode=ApprovalMode.AUTO,
        depends_on=["market"], # 시장 분석(타겟) 필요
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
            # 순환 의존성 발생 시 비상 탈출 (남은거 순차 처리)
            layer = list(remaining)
            # break or handle error
        
        # 이름순/우선순위 정렬 (결정적 순서 보장)
        priority = ["market", "tech", "bm", "content", "financial", "risk"]
        layer.sort(key=lambda x: priority.index(x) if x in priority else 99)
        
        layers.append(layer)
        
        # 상태 업데이트
        for agent in layer:
            remaining.remove(agent)
            completed.add(agent)

    # 3. Plan 객체 생성
    steps = []
    total_time = 0
    
    for i, layer_agents in enumerate(layers):
        # 단계별 설명 생성
        desc = f"분석 단계 {i+1}: {', '.join([AGENT_REGISTRY[a].name for a in layer_agents])}"
        
        # 예상 시간 (병렬이므로 레이어 내 최대 시간)
        layer_time = max([AGENT_REGISTRY[a].timeout_seconds for a in layer_agents], default=0)
        total_time += layer_time
        
        steps.append(ExecutionStep(
            step_id=i+1,
            agent_ids=layer_agents,
            description=desc
        ))
        
    return ExecutionPlan(
        steps=steps,
        reasoning=reasoning,
        total_estimated_time=total_time
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


def get_agents_for_purpose(purpose: str) -> List[str]:
    """
    목적에 따른 권장 에이전트 목록 반환
    
    Args:
        purpose: 분석 목적 (기획서/투자유치/아이디어검증 등)
    """
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
