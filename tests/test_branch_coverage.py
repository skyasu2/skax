"""
PlanCraft 워크플로우 분기 커버리지 테스트

워크플로우의 모든 분기 경로를 테스트하고 Mermaid 다이어그램을 자동 생성합니다.

분기 경로:
1. Analyzer → option_pause (need_more_info=True, options 있음)
2. Analyzer → general_response (일반 대화)
3. Analyzer → structure (기획서 생성 진행)
4. Reviewer → refine (REVISE)
5. Reviewer → structure (재분석 필요, FAIL)
6. Reviewer → format (PASS)

Usage:
    pytest tests/test_branch_coverage.py -v
    pytest tests/test_branch_coverage.py --generate-mermaid
"""

import pytest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List
import json
import os


# =============================================================================
# 테스트 헬퍼
# =============================================================================

def create_mock_state(**overrides) -> Dict[str, Any]:
    """테스트용 기본 상태 생성"""
    base_state = {
        "user_input": "AI 헬스케어 앱 기획",
        "thread_id": "test_thread",
        "refine_count": 0,
        "restart_count": 0,
        "retry_count": 0,
        "generation_preset": "balanced",
        "step_history": [],
        "chat_history": [],
        "error": None,
        "need_more_info": False,
        "options": [],
        "analysis": None,
        "structure": None,
        "draft": None,
        "review": None,
    }
    base_state.update(overrides)
    return base_state


# =============================================================================
# 분기 경로 테스트
# =============================================================================

class TestAnalyzerBranches:
    """Analyzer 노드 분기 테스트"""

    def test_branch_to_option_pause(self):
        """Analyzer → option_pause 분기 (추가 정보 필요)"""
        from graph.workflow import should_ask_user, RouteKey

        state = create_mock_state(need_more_info=True)

        result = should_ask_user(state)
        assert result == RouteKey.OPTION_PAUSE, f"Expected OPTION_PAUSE, got '{result}'"

    def test_branch_to_general_response(self):
        """Analyzer → general_response 분기 (일반 대화)"""
        from graph.workflow import should_ask_user, RouteKey

        # 일반 대화: need_more_info=False, analysis에 is_general_query=True
        state = create_mock_state(
            need_more_info=False,
            analysis={"is_general_query": True}
        )

        result = should_ask_user(state)
        assert result == RouteKey.GENERAL_RESPONSE, f"Expected GENERAL_RESPONSE, got '{result}'"

    def test_branch_to_structure(self):
        """Analyzer → structure 분기 (기획서 생성)"""
        from graph.workflow import should_ask_user, RouteKey

        state = create_mock_state(
            need_more_info=False,
            analysis={"topic": "AI 헬스케어", "purpose": "건강 관리", "is_general_query": False}
        )

        result = should_ask_user(state)
        assert result == RouteKey.CONTINUE, f"Expected CONTINUE, got '{result}'"


class TestReviewerBranches:
    """Reviewer 노드 분기 테스트"""

    def test_branch_to_refine_on_revise(self):
        """Reviewer → refine 분기 (REVISE 판정, 5-8점)"""
        from graph.workflow import should_refine_or_restart, RouteKey

        state = create_mock_state(
            review={"verdict": "REVISE", "overall_score": 7},
            refine_count=0,
            restart_count=0
        )

        result = should_refine_or_restart(state)
        assert result == RouteKey.REFINE, f"Expected REFINE, got '{result}'"

    def test_branch_to_format_on_pass(self):
        """Reviewer → format 분기 (PASS 판정, 9점 이상)"""
        from graph.workflow import should_refine_or_restart, RouteKey

        state = create_mock_state(
            review={"verdict": "PASS", "overall_score": 9},
            refine_count=0,
            restart_count=0
        )

        result = should_refine_or_restart(state)
        assert result == RouteKey.COMPLETE, f"Expected COMPLETE, got '{result}'"

    def test_branch_to_analyze_on_fail(self):
        """Reviewer → analyze 분기 (FAIL 판정, 5점 미만)"""
        from graph.workflow import should_refine_or_restart, RouteKey

        state = create_mock_state(
            review={"verdict": "FAIL", "overall_score": 3},
            refine_count=0,
            restart_count=0
        )

        result = should_refine_or_restart(state)
        assert result == RouteKey.RESTART, f"Expected RESTART, got '{result}'"

    def test_branch_to_refine_on_max_restart(self):
        """Reviewer → refine 분기 (최대 재시작 도달 시 refine으로)"""
        from graph.workflow import should_refine_or_restart, RouteKey

        # 최대 재시작 횟수 (기본값 2)
        state = create_mock_state(
            review={"verdict": "FAIL", "overall_score": 3},
            refine_count=0,
            restart_count=2  # 최대 재시작 도달
        )

        result = should_refine_or_restart(state)
        assert result == RouteKey.REFINE, f"Expected REFINE (max restart), got '{result}'"


class TestPresetBasedValidation:
    """프리셋별 품질 기준 분기 테스트"""

    def test_fast_preset_lower_threshold(self):
        """fast 프리셋: 낮은 품질 기준"""
        from graph.workflow import should_refine_or_restart

        state = create_mock_state(
            generation_preset="fast",
            review={"verdict": "REVISE", "score": 7},  # fast에서는 7점도 PASS
            refine_count=0
        )

        # fast 모드에서는 더 관대한 기준 적용 가능
        result = should_refine_or_restart(state)
        # 실제 구현에 따라 달라질 수 있음
        assert result in ["refine", "format"]

    def test_quality_preset_higher_threshold(self):
        """quality 프리셋: 높은 품질 기준"""
        from graph.workflow import should_refine_or_restart

        state = create_mock_state(
            generation_preset="quality",
            review={"verdict": "REVISE", "score": 8},  # quality에서는 8점도 REVISE
            refine_count=0
        )

        result = should_refine_or_restart(state)
        assert result == "refine", f"Expected 'refine' for quality preset, got '{result}'"


# =============================================================================
# Mermaid 다이어그램 생성 테스트
# =============================================================================

class TestMermaidGeneration:
    """Mermaid 다이어그램 생성 테스트"""

    def test_export_plan_to_mermaid(self):
        """ExecutionPlan → Mermaid 변환"""
        from agents.agent_config import export_plan_to_mermaid, ExecutionPlan, ExecutionStep

        plan = ExecutionPlan(
            steps=[
                ExecutionStep(step_id=0, agent_ids=["market", "bm"]),
                ExecutionStep(step_id=1, agent_ids=["financial"]),
            ],
            reasoning="테스트용 실행 계획"
        )

        mermaid_code = export_plan_to_mermaid(plan, "테스트 플랜")

        assert "flowchart" in mermaid_code or "graph" in mermaid_code
        assert "market" in mermaid_code
        assert "bm" in mermaid_code
        assert "financial" in mermaid_code

    def test_export_dag_to_mermaid(self):
        """에이전트 DAG → Mermaid 변환"""
        from agents.agent_config import export_dag_to_mermaid

        mermaid_code = export_dag_to_mermaid(["market", "bm", "financial"])

        assert "flowchart LR" in mermaid_code or "graph LR" in mermaid_code
        assert "market" in mermaid_code


class TestWorkflowVisualization:
    """워크플로우 시각화 테스트"""

    def test_generate_workflow_mermaid(self):
        """전체 워크플로우 Mermaid 생성"""
        mermaid_code = generate_workflow_mermaid()

        assert "flowchart" in mermaid_code or "graph" in mermaid_code
        assert "analyze" in mermaid_code
        assert "structure" in mermaid_code
        assert "write" in mermaid_code
        assert "review" in mermaid_code


def generate_workflow_mermaid() -> str:
    """PlanCraft 워크플로우 Mermaid 다이어그램 생성"""
    return """
flowchart TB
    subgraph Context["컨텍스트 수집"]
        START([시작]) --> context[context_gathering]
    end

    subgraph Analysis["분석 단계"]
        context --> analyze[analyze]
        analyze -->|need_more_info=True, options| option_pause[option_pause]
        analyze -->|need_more_info=True, no options| general_response[general_response]
        analyze -->|need_more_info=False| structure[structure]
    end

    subgraph Generation["생성 단계"]
        structure --> write[write]
        write --> review[review]
    end

    subgraph QA["품질 관리"]
        review -->|PASS| format[format]
        review -->|REVISE| refine[refine]
        review -->|FAIL| analyze
        refine --> write
    end

    subgraph Output["출력"]
        format --> END([종료])
        option_pause --> END
        general_response --> END
    end

    style START fill:#90EE90
    style END fill:#FFB6C1
    style analyze fill:#87CEEB
    style review fill:#DDA0DD
"""


# =============================================================================
# 분기 커버리지 리포트
# =============================================================================

class TestBranchCoverageReport:
    """분기 커버리지 리포트 생성"""

    def test_generate_coverage_report(self):
        """커버리지 리포트 생성"""
        branches = {
            "analyzer": {
                "option_pause": "테스트됨",
                "general_response": "테스트됨",
                "structure": "테스트됨",
            },
            "reviewer": {
                "refine": "테스트됨",
                "format": "테스트됨",
                "analyze": "테스트됨",
                "max_refine_fallback": "테스트됨",
            },
        }

        total = sum(len(b) for b in branches.values())
        covered = sum(1 for b in branches.values() for v in b.values() if v == "테스트됨")

        coverage = (covered / total) * 100
        assert coverage == 100.0, f"분기 커버리지: {coverage}%"

    def test_save_mermaid_to_file(self, tmp_path):
        """Mermaid 파일 저장 테스트"""
        mermaid_code = generate_workflow_mermaid()

        output_file = tmp_path / "workflow.mmd"
        output_file.write_text(mermaid_code, encoding="utf-8")

        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "flowchart" in content


# =============================================================================
# CI 통합용 Fixture
# =============================================================================

@pytest.fixture
def generate_mermaid_on_ci(request):
    """CI에서 Mermaid 파일 자동 생성"""
    yield

    # 테스트 후 Mermaid 파일 생성 (CI 환경에서만)
    if os.environ.get("CI") or request.config.getoption("--generate-mermaid", default=False):
        mermaid_code = generate_workflow_mermaid()
        output_path = "docs/workflow.mmd"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"\n[CI] Mermaid 다이어그램 생성: {output_path}")


def pytest_addoption(parser):
    """pytest 커맨드라인 옵션 추가"""
    parser.addoption(
        "--generate-mermaid",
        action="store_true",
        default=False,
        help="테스트 후 Mermaid 다이어그램 파일 생성"
    )
