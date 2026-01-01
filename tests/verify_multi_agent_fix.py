import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.supervisor import PlanSupervisor
from agents.agent_config import AGENT_REGISTRY

def test_supervisor_initialization():
    print("1. Supervisor 초기화 테스트...")
    try:
        # 수정된 부분: 인자 없이 호출 (Writer에서 호출하는 방식)
        supervisor = PlanSupervisor()
        print("   ✅ Supervisor 초기화 성공 (PlanSupervisor() 호출)")
        
        # 에이전트 로드 확인
        print(f"2. 에이전트 로드 확인 (총 {len(supervisor.agents)}개)...")
        loaded_agents = set(supervisor.agents.keys())
        expected_agents = set(AGENT_REGISTRY.keys())
        
        if loaded_agents == expected_agents:
            print(f"   ✅ 모든 전문 에이전트가 정상적으로 로드됨: {loaded_agents}")
        else:
            print(f"   ❌ 에이전트 불일치: 로드됨={loaded_agents} / 기대={expected_agents}")
            
        return supervisor
    except TypeError as e:
        print(f"   ❌ 초기화 실패: {e}")
        if "unexpected keyword argument 'parallel'" in str(e):
            print("      -> CRITICAL: 'parallel' 인자 관련 버그가 아직 수정되지 않았습니다.")
        return None
    except Exception as e:
        print(f"   ❌ 초기화 실패 (기타 오류): {e}")
        return None

def test_dependency_resolution(supervisor):
    if not supervisor:
        return
        
    print("3. 의존성 해결 로직 테스트 (Config 기반)...")
    
    # 시나리오 1: Financial만 요청했을 때 (BM 의존성 자동 추가 확인)
    required = ["financial"]
    order = supervisor._resolve_dependencies(required)
    print(f"   [시나리오 1] 요청='financial' -> 실행순서={order}")
    
    if "bm" in order and order.index("bm") < order.index("financial"):
        print("   ✅ 성공: BM이 Financial보다 먼저 실행됨")
    else:
        print("   ❌ 실패: 의존성 순서가 올바르지 않음")

    # 시나리오 2: Risk와 Market 요청 (독립 및 의존성 혼합)
    required = ["risk", "market"]
    order = supervisor._resolve_dependencies(required)
    print(f"   [시나리오 2] 요청='risk', 'market' -> 실행순서={order}")
    
    # market(독립) -> bm(risk의존) -> risk 순서 예상
    if "market" in order and "bm" in order and "risk" in order:
        print("   ✅ 성공: Market, BM(자동추가), Risk가 모두 포함됨")
    else:
        print("   ❌ 실패: 일부 에이전트 누락")

if __name__ == "__main__":
    print("=== Multi-Agent 수정 사항 검증 시작 ===")
    mock_sup = test_supervisor_initialization()
    if mock_sup:
        test_dependency_resolution(mock_sup)
    print("=== 검증 종료 ===")
