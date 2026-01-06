"""
PlanCraft Test Configuration

테스트 간 격리 및 공통 fixture 설정.
"""

import pytest
import sys
import importlib


@pytest.fixture(autouse=True)
def reset_module_cache():
    """
    각 테스트 후 모듈 캐시 초기화.

    테스트에서 mock.patch가 모듈을 변경하면,
    다음 테스트에 영향을 줄 수 있음.
    이 fixture는 테스트 간 격리를 보장.
    """
    yield

    # 테스트 후 agents 모듈 캐시 초기화
    if hasattr(sys.modules.get('agents', None), '_module_cache'):
        sys.modules['agents']._module_cache.clear()


@pytest.fixture(autouse=True)
def clear_lru_cache():
    """
    LRU 캐시가 있는 함수들 초기화.
    """
    yield

    # 캐시가 있는 함수들 clear
    try:
        from utils.settings import get_preset
        if hasattr(get_preset, 'cache_clear'):
            get_preset.cache_clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture
def mock_llm():
    """
    Mock LLM fixture for tests that don't need real API calls.
    """
    from unittest.mock import MagicMock, patch

    mock = MagicMock()
    mock.invoke.return_value = MagicMock(content="Mock response")

    with patch('utils.llm.get_llm', return_value=mock):
        yield mock


@pytest.fixture
def sample_state():
    """
    테스트용 기본 PlanCraftState.
    """
    from graph.state import create_initial_state
    return create_initial_state("테스트용 아이디어 입력")


@pytest.fixture
def sample_analysis_result():
    """
    테스트용 AnalysisResult.
    """
    from utils.schemas import AnalysisResult
    return AnalysisResult(
        topic="테스트 서비스",
        purpose="기획서 작성",
        target_users="테스트 사용자",
        key_features=["기능1", "기능2", "기능3"],
        need_more_info=False
    )


@pytest.fixture
def sample_structure_result():
    """
    테스트용 StructureResult.
    """
    from utils.schemas import StructureResult, SectionStructure
    return StructureResult(
        title="테스트 기획서",
        sections=[
            SectionStructure(id=1, name="개요", description="서비스 개요", key_points=[]),
            SectionStructure(id=2, name="시장분석", description="시장 분석", key_points=[]),
            SectionStructure(id=3, name="비즈니스모델", description="수익 모델", key_points=[]),
        ]
    )
