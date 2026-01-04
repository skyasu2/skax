
import pytest
import sys
import os
from unittest.mock import MagicMock

# 현재 디렉토리를 sys.path에 추가
sys.path.insert(0, os.getcwd())

# -----------------------------------------------------------------------------
# Dependency Injection / Mocking (순환 참조 및 외부 의존성 제거)
# -----------------------------------------------------------------------------
# 1. Prompts modules
prompts_mock = MagicMock()
prompts_mock.writer_prompt.WRITER_SYSTEM_PROMPT = "MOCK_WRITER_SYSTEM"
prompts_mock.writer_prompt.WRITER_USER_PROMPT = "MOCK_WRITER_USER"
prompts_mock.business_plan_prompt.BUSINESS_PLAN_SYSTEM_PROMPT = "MOCK_BIZ_SYSTEM"
prompts_mock.business_plan_prompt.BUSINESS_PLAN_USER_PROMPT = "MOCK_BIZ_USER"

# sys.modules["prompts"] = prompts_mock  <-- REMOVE (Let Python find the real package dir)
sys.modules["prompts.writer_prompt"] = prompts_mock.writer_prompt
sys.modules["prompts.business_plan_prompt"] = prompts_mock.business_plan_prompt

# 2. Utils sub-modules (Do NOT mock top-level 'utils' package)
sys.modules["utils.file_logger"] = MagicMock()

# 3. Graph sub-modules (Do NOT mock top-level 'graph' package)
graph_state_mock = MagicMock()
def side_effect_ensure_dict(x):
    return x if isinstance(x, dict) else {}
graph_state_mock.ensure_dict = side_effect_ensure_dict
sys.modules["graph.state"] = graph_state_mock

# -----------------------------------------------------------------------------
# Import Target Module
# -----------------------------------------------------------------------------
from agents.helpers.prompt_builder import (
    get_prompts_by_doc_type,
    build_refinement_context, 
    build_visual_instruction
)
from types import SimpleNamespace

class MockLogger:
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

def test_get_prompts_by_doc_type():
    print("Running test_get_prompts_by_doc_type...")
    # Case 1: Business Plan (dict access via ensure_dict mock)
    state_biz = {"analysis": {"doc_type": "business_plan"}}
    sys_p, user_p = get_prompts_by_doc_type(state_biz)
    assert sys_p == "MOCK_BIZ_SYSTEM"
    assert user_p == "MOCK_BIZ_USER"
    
    # Case 2: Web App Plan (Default)
    state_web = {"analysis": {"doc_type": "web_app_plan"}}
    sys_p, user_p = get_prompts_by_doc_type(state_web)
    assert sys_p == "MOCK_WRITER_SYSTEM"
    assert user_p == "MOCK_WRITER_USER"
    print("PASS")

def test_build_refinement_context_initial():
    print("Running test_build_refinement_context_initial...")
    res = build_refinement_context(0, 3)
    assert res == "", f"Expected empty string, got {res}"
    print("PASS")

def test_build_refinement_context_retry():
    print("Running test_build_refinement_context_retry...")
    ctx = build_refinement_context(1, min_sections=5)
    assert "REFINEMENT MODE" in ctx
    # assert "5개 이상의 섹션" in ctx <-- Fixed
    assert "정확히 5개 이상" in ctx
    print("PASS")

def test_build_visual_instruction_no_visuals():
    print("Running test_build_visual_instruction_no_visuals...")
    preset = SimpleNamespace(include_diagrams=0, include_charts=0)
    logger = MockLogger()
    res = build_visual_instruction(preset, logger)
    assert res == "", f"Expected empty string, got {res}"
    print("PASS")

def test_build_visual_instruction_with_diagrams():
    print("Running test_build_visual_instruction_with_diagrams...")
    preset = SimpleNamespace(
        include_diagrams=1, 
        include_charts=0,
        diagram_types=['flowchart'],
        diagram_direction='LR',
        diagram_theme='forest'
    )
    logger = MockLogger()
    ctx = build_visual_instruction(preset, logger)
    assert "Mermaid 다이어그램" in ctx
    assert "flowchart" in ctx
    assert "forest" in ctx
    assert "LR" in ctx
    print("PASS")

def test_build_visual_instruction_with_charts():
    print("Running test_build_visual_instruction_with_charts...")
    preset = SimpleNamespace(
        include_diagrams=0, 
        include_charts=2
    )
    logger = MockLogger()
    ctx = build_visual_instruction(preset, logger)
    assert "ASCII 막대 그래프" in ctx
    assert "2개 이상 필수" in ctx
    print("PASS")

if __name__ == "__main__":
    try:
        test_get_prompts_by_doc_type()
        test_build_refinement_context_initial()
        test_build_refinement_context_retry()
        test_build_visual_instruction_no_visuals()
        test_build_visual_instruction_with_diagrams()
        test_build_visual_instruction_with_charts()
        print("ALL TESTS PASSED SUCCESSFULLY")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
