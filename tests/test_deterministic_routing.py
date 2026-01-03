"""
결정론적 라우팅 테스트 (Deterministic Routing Tests)

Supervisor의 규칙 기반 라우팅이 일관되게 동작하는지 검증합니다.

Key Principles:
1. 동일 입력 → 동일 출력 (결정론적)
2. 키워드 기반 에이전트 선택 (tech, content)
3. 목적 기반 필수 에이전트 (기획서 vs 아이디어 검증)
"""

import pytest
from agents.supervisor import (
    detect_required_agents,
    RoutingDecision,
    TECH_KEYWORDS,
    CONTENT_KEYWORDS,
)


class TestDeterministicRouting:
    """규칙 기반 라우팅 결정론성 테스트"""

    def test_same_input_same_output(self):
        """동일 입력 시 항상 동일한 결과 반환"""
        service = "AI 기반 점심 추천 앱"
        purpose = "기획서 작성"

        # 100번 호출해도 동일한 결과
        results = [
            detect_required_agents(service, purpose)
            for _ in range(100)
        ]

        first_result = results[0]
        for result in results[1:]:
            assert result.required_analyses == first_result.required_analyses
            assert result.reasoning == first_result.reasoning

    def test_returns_routing_decision_type(self):
        """RoutingDecision 타입 반환"""
        result = detect_required_agents("서비스", "기획서 작성")
        assert isinstance(result, RoutingDecision)
        assert hasattr(result, "required_analyses")
        assert hasattr(result, "reasoning")


class TestPurposeBasedRouting:
    """목적 기반 라우팅 테스트"""

    def test_planning_purpose_includes_all_core_agents(self):
        """기획서 작성 목적 → 4대 필수 에이전트 포함"""
        result = detect_required_agents("카페 창업", "기획서 작성")

        core_agents = ["market", "bm", "financial", "risk"]
        for agent in core_agents:
            assert agent in result.required_analyses, f"{agent} 누락"

    def test_idea_validation_includes_only_market_bm(self):
        """아이디어 검증 목적 → market, bm만 포함"""
        result = detect_required_agents("카페 창업", "아이디어 검증")

        assert "market" in result.required_analyses
        assert "bm" in result.required_analyses
        # financial, risk는 미포함
        assert "financial" not in result.required_analyses
        assert "risk" not in result.required_analyses

    def test_default_purpose_is_planning(self):
        """기본 목적은 기획서 작성"""
        result = detect_required_agents("서비스")  # purpose 미지정

        core_agents = ["market", "bm", "financial", "risk"]
        for agent in core_agents:
            assert agent in result.required_analyses


class TestTechKeywordRouting:
    """tech 에이전트 키워드 기반 라우팅"""

    @pytest.mark.parametrize("keyword", [
        "앱", "웹", "플랫폼", "개발", "ai", "블록체인",
        "api", "서버", "클라우드", "모바일", "saas"
    ])
    def test_tech_keywords_trigger_tech_agent(self, keyword):
        """기술 키워드 → tech 에이전트 포함"""
        result = detect_required_agents(f"{keyword} 기반 서비스", "기획서 작성")
        assert "tech" in result.required_analyses

    def test_no_tech_keyword_no_tech_agent(self):
        """기술 키워드 없음 → tech 에이전트 미포함"""
        result = detect_required_agents("카페 창업 사업 계획", "기획서 작성")
        assert "tech" not in result.required_analyses

    def test_tech_keyword_case_insensitive(self):
        """대소문자 무관하게 감지"""
        result1 = detect_required_agents("AI 서비스", "기획서 작성")
        result2 = detect_required_agents("ai 서비스", "기획서 작성")
        result3 = detect_required_agents("Ai 서비스", "기획서 작성")

        assert "tech" in result1.required_analyses
        assert "tech" in result2.required_analyses
        assert "tech" in result3.required_analyses


class TestContentKeywordRouting:
    """content 에이전트 키워드 기반 라우팅"""

    @pytest.mark.parametrize("keyword", [
        "커뮤니티", "sns", "마케팅", "콘텐츠", "브랜드",
        "홍보", "인플루언서", "유튜브", "인스타"
    ])
    def test_content_keywords_trigger_content_agent(self, keyword):
        """콘텐츠 키워드 → content 에이전트 포함"""
        result = detect_required_agents(f"{keyword} 중심 사업", "기획서 작성")
        assert "content" in result.required_analyses

    def test_no_content_keyword_no_content_agent(self):
        """콘텐츠 키워드 없음 → content 에이전트 미포함"""
        result = detect_required_agents("B2B 물류 시스템", "기획서 작성")
        assert "content" not in result.required_analyses


class TestCombinedKeywordRouting:
    """복합 키워드 라우팅 테스트"""

    def test_both_tech_and_content(self):
        """기술 + 콘텐츠 키워드 → 둘 다 포함"""
        result = detect_required_agents(
            "AI 기반 인플루언서 마케팅 플랫폼",
            "기획서 작성"
        )

        assert "tech" in result.required_analyses  # AI, 플랫폼
        assert "content" in result.required_analyses  # 인플루언서, 마케팅

    def test_complex_service_description(self):
        """복잡한 서비스 설명도 정확히 분석"""
        result = detect_required_agents(
            "React Native 기반 음식 배달 앱으로, 유튜브 크리에이터와 협업하여 마케팅",
            "기획서 작성"
        )

        # 모든 에이전트 포함
        assert "market" in result.required_analyses
        assert "bm" in result.required_analyses
        assert "financial" in result.required_analyses
        assert "risk" in result.required_analyses
        assert "tech" in result.required_analyses  # React Native, 앱
        assert "content" in result.required_analyses  # 유튜브, 크리에이터, 마케팅


class TestReasoningOutput:
    """라우팅 이유 출력 테스트"""

    def test_reasoning_includes_purpose(self):
        """reasoning에 목적 관련 설명 포함"""
        result = detect_required_agents("서비스", "기획서 작성")
        assert "기획서" in result.reasoning

    def test_reasoning_includes_detected_keywords(self):
        """reasoning에 감지된 키워드 포함"""
        result = detect_required_agents("AI 기반 앱", "기획서 작성")
        assert "키워드" in result.reasoning or "감지" in result.reasoning

    def test_reasoning_is_not_empty(self):
        """reasoning이 비어있지 않음"""
        result = detect_required_agents("서비스", "기획서 작성")
        assert len(result.reasoning) > 0


class TestKeywordSets:
    """키워드 세트 검증"""

    def test_tech_keywords_is_frozenset(self):
        """TECH_KEYWORDS는 불변 집합"""
        assert isinstance(TECH_KEYWORDS, frozenset)

    def test_content_keywords_is_frozenset(self):
        """CONTENT_KEYWORDS는 불변 집합"""
        assert isinstance(CONTENT_KEYWORDS, frozenset)

    def test_tech_keywords_all_lowercase(self):
        """TECH_KEYWORDS는 모두 소문자"""
        for kw in TECH_KEYWORDS:
            assert kw == kw.lower(), f"'{kw}'는 소문자여야 함"

    def test_content_keywords_all_lowercase(self):
        """CONTENT_KEYWORDS는 모두 소문자"""
        for kw in CONTENT_KEYWORDS:
            assert kw == kw.lower(), f"'{kw}'는 소문자여야 함"


class TestBackwardCompatibility:
    """하위 호환성 테스트"""

    def test_supervisor_uses_rule_based_by_default(self):
        """Supervisor는 기본적으로 규칙 기반 라우팅 사용"""
        from agents.supervisor import NativeSupervisor

        # NativeSupervisor 인스턴스 생성 (에이전트 초기화 실패해도 OK)
        try:
            supervisor = NativeSupervisor()
        except Exception:
            pytest.skip("Supervisor 초기화 실패 (에이전트 미설치)")

        # decide_required_agents의 기본값 확인
        import inspect
        sig = inspect.signature(supervisor.decide_required_agents)
        use_llm_param = sig.parameters.get("use_llm_routing")

        assert use_llm_param is not None
        assert use_llm_param.default is False

    def test_detect_required_agents_is_exported(self):
        """detect_required_agents가 export됨"""
        from agents.supervisor import detect_required_agents
        assert callable(detect_required_agents)
