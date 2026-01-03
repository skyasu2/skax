"""
Agent Registry 정합성 테스트

AGENT_REGISTRY의 각 에이전트가 올바르게 설정되어 있는지 검증합니다.
- result_key 고유성 및 형식
- class_path 유효성 (실제 클래스 존재 여부)
- 의존성 그래프 무결성
"""
import sys
import os
import unittest
import importlib

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.agent_config import AGENT_REGISTRY, AgentSpec


class TestAgentRegistryConsistency(unittest.TestCase):
    """Agent Registry 정합성 테스트"""

    def test_all_agents_have_unique_ids(self):
        """모든 에이전트가 고유한 ID를 가지는지 확인"""
        agent_ids = list(AGENT_REGISTRY.keys())
        self.assertEqual(len(agent_ids), len(set(agent_ids)), "중복된 agent_id가 존재합니다")

    def test_all_agents_have_unique_result_keys(self):
        """모든 에이전트가 고유한 result_key를 가지는지 확인"""
        result_keys = [spec.result_key for spec in AGENT_REGISTRY.values()]
        self.assertEqual(
            len(result_keys),
            len(set(result_keys)),
            f"중복된 result_key가 존재합니다: {result_keys}"
        )

    def test_result_key_format(self):
        """result_key가 올바른 형식인지 확인 (snake_case)"""
        import re
        snake_case_pattern = re.compile(r'^[a-z][a-z0-9_]*$')

        for agent_id, spec in AGENT_REGISTRY.items():
            with self.subTest(agent_id=agent_id):
                self.assertTrue(
                    snake_case_pattern.match(spec.result_key),
                    f"result_key '{spec.result_key}'가 snake_case 형식이 아닙니다"
                )

    def test_class_path_not_empty(self):
        """모든 에이전트가 class_path를 가지는지 확인"""
        for agent_id, spec in AGENT_REGISTRY.items():
            with self.subTest(agent_id=agent_id):
                self.assertTrue(
                    spec.class_path,
                    f"에이전트 '{agent_id}'의 class_path가 비어있습니다"
                )

    def test_class_path_is_importable(self):
        """class_path가 실제로 import 가능한지 확인"""
        for agent_id, spec in AGENT_REGISTRY.items():
            if not spec.class_path:
                continue

            with self.subTest(agent_id=agent_id, class_path=spec.class_path):
                try:
                    # class_path 파싱: "agents.specialists.market_agent.MarketAgent"
                    parts = spec.class_path.rsplit('.', 1)
                    if len(parts) == 2:
                        module_path, class_name = parts
                        module = importlib.import_module(module_path)
                        self.assertTrue(
                            hasattr(module, class_name),
                            f"모듈 '{module_path}'에 클래스 '{class_name}'가 없습니다"
                        )
                except ImportError as e:
                    self.fail(f"class_path '{spec.class_path}' import 실패: {e}")

    def test_dependencies_exist_in_registry(self):
        """의존성으로 지정된 에이전트가 실제로 Registry에 존재하는지 확인"""
        all_agent_ids = set(AGENT_REGISTRY.keys())

        for agent_id, spec in AGENT_REGISTRY.items():
            for dep in spec.depends_on:
                with self.subTest(agent_id=agent_id, dependency=dep):
                    self.assertIn(
                        dep,
                        all_agent_ids,
                        f"에이전트 '{agent_id}'의 의존성 '{dep}'가 Registry에 없습니다"
                    )

    def test_agent_id_matches_result_key_pattern(self):
        """agent_id와 result_key 간 일관성 확인"""
        for agent_id, spec in AGENT_REGISTRY.items():
            with self.subTest(agent_id=agent_id):
                # result_key는 agent_id를 포함하거나, 명확한 매핑이어야 함
                # 예: "market" -> "market_analysis", "bm" -> "business_model"
                self.assertTrue(
                    agent_id in spec.result_key or spec.result_key in ["business_model"],
                    f"agent_id '{agent_id}'와 result_key '{spec.result_key}' 간 관계가 불명확합니다"
                )

    def test_no_self_dependency(self):
        """에이전트가 자기 자신에 의존하지 않는지 확인"""
        for agent_id, spec in AGENT_REGISTRY.items():
            with self.subTest(agent_id=agent_id):
                self.assertNotIn(
                    agent_id,
                    spec.depends_on,
                    f"에이전트 '{agent_id}'가 자기 자신에 의존합니다"
                )

    def test_required_fields_present(self):
        """필수 필드가 모두 존재하는지 확인"""
        required_fields = ['id', 'name', 'description', 'result_key']

        for agent_id, spec in AGENT_REGISTRY.items():
            with self.subTest(agent_id=agent_id):
                self.assertEqual(spec.id, agent_id, "spec.id와 registry key가 불일치")
                self.assertTrue(spec.name, "name이 비어있습니다")
                self.assertTrue(spec.description, "description이 비어있습니다")
                self.assertTrue(spec.result_key, "result_key가 비어있습니다")


class TestAgentSpecDataclass(unittest.TestCase):
    """AgentSpec 데이터클래스 테스트"""

    def test_spec_to_dict(self):
        """AgentSpec.to_dict() 메서드가 올바르게 동작하는지 확인"""
        spec = AGENT_REGISTRY.get("market")
        if spec:
            spec_dict = spec.to_dict()
            self.assertIn("id", spec_dict)
            self.assertIn("name", spec_dict)
            self.assertIn("result_key", spec_dict)
            self.assertIn("class_path", spec_dict)

    def test_default_result_key_generation(self):
        """result_key 기본값 자동 생성 로직 테스트"""
        # 새 AgentSpec 생성 시 result_key가 자동으로 설정되어야 함
        spec = AgentSpec(
            id="test_agent",
            name="Test Agent",
            description="테스트용",
            icon="🧪"
        )
        self.assertEqual(spec.result_key, "test_agent_analysis")


if __name__ == "__main__":
    unittest.main()
