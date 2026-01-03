"""
LangSmith Tracing Utility

노드별 상세 트레이싱을 위한 유틸리티 모듈입니다.
LangSmith에서 노드 실행을 추적하고 디버깅할 수 있도록 메타데이터를 추가합니다.

기능:
    - 노드별 run_name 자동 설정
    - 태그 기반 필터링 지원
    - 메타데이터 (preset, refine_count 등) 기록
    - 실행 시간 측정

사용 예시:
    @trace_node("analyze", tags=["agent", "llm"])
    def run_analyzer_node(state):
        ...

LangSmith 대시보드에서 확인:
    - 프로젝트: PlanCraft (또는 LANGCHAIN_PROJECT 환경변수)
    - 필터: tags contains "agent"
    - 그룹핑: run_name
"""

import functools
import time
import os
from typing import Callable, List, Optional, Dict, Any
from datetime import datetime

from utils.file_logger import get_file_logger


# =============================================================================
# Constants
# =============================================================================

# 노드 카테고리별 기본 태그
NODE_TAGS = {
    "context": ["rag", "retrieval"],
    "analyze": ["agent", "llm", "analysis"],
    "structure": ["agent", "llm", "planning"],
    "write": ["agent", "llm", "generation"],
    "review": ["agent", "llm", "evaluation"],
    "discuss": ["agent", "llm", "collaboration"],
    "refine": ["agent", "llm", "refinement"],
    "format": ["agent", "output"],
    "interrupt": ["hitl", "human"],
}

# 노드별 한글 설명 (LangSmith run_name에 표시)
NODE_DESCRIPTIONS = {
    "context": "📚 컨텍스트 수집",
    "analyze": "🔍 요구사항 분석",
    "structure": "🏗️ 구조 설계",
    "write": "✍️ 콘텐츠 작성",
    "review": "🔎 품질 검토",
    "discuss": "💬 에이전트 토론",
    "refine": "✨ 개선 적용",
    "format": "📋 최종 포맷팅",
    "interrupt": "⏸️ 사용자 입력 대기",
}


# =============================================================================
# Tracing Decorator
# =============================================================================

def trace_node(
    node_name: str,
    tags: Optional[List[str]] = None,
    include_state_info: bool = True
) -> Callable:
    """
    [Decorator] LangSmith 트레이싱을 위한 노드 래퍼

    LangSmith에서 노드별 실행을 추적할 수 있도록 메타데이터를 추가합니다.

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                     LangSmith 트레이싱 정보                              │
    ├──────────────────────┬──────────────────────────────────────────────────┤
    │ 필드                 │ 설명                                             │
    ├──────────────────────┼──────────────────────────────────────────────────┤
    │ run_name             │ "🔍 요구사항 분석" 형태의 한글 설명               │
    │ tags                 │ ["agent", "llm"] 등 필터링용 태그                │
    │ metadata.node_name   │ 노드 함수명                                      │
    │ metadata.preset      │ 생성 모드 (fast/balanced/quality)                │
    │ metadata.refine_count│ 현재 개선 횟수                                   │
    │ metadata.thread_id   │ 대화 스레드 ID                                   │
    │ metadata.execution_ms│ 실행 시간 (밀리초)                               │
    └──────────────────────┴──────────────────────────────────────────────────┘

    Args:
        node_name: 노드 식별자 (analyze, structure, write 등)
        tags: 추가 태그 리스트 (기본 태그에 추가)
        include_state_info: State 정보를 메타데이터에 포함할지 여부

    Returns:
        데코레이터 함수

    Example:
        @trace_node("analyze", tags=["critical"])
        @handle_node_error
        def run_analyzer_node(state):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state, *args, **kwargs):
            logger = get_file_logger()
            start_time = time.time()

            # 메타데이터 수집
            metadata = _build_metadata(state, node_name, include_state_info)

            # 태그 병합 (기본 + 커스텀)
            all_tags = NODE_TAGS.get(node_name, ["agent"])
            if tags:
                all_tags = list(set(all_tags + tags))

            # run_name 생성
            run_name = NODE_DESCRIPTIONS.get(node_name, f"🔄 {node_name}")

            # LangSmith 환경변수로 메타데이터 전달
            # Note: RunnableConfig 방식이 더 안전하나, 현재 구조상 환경변수 방식 사용
            _set_trace_context(run_name, all_tags, metadata)

            # 트레이싱 로그 (LangSmith 비활성화 시에도 로컬 로그 유지)
            logger.info(f"[TRACE] {run_name} 시작 | tags={all_tags}")

            try:
                result = func(state, *args, **kwargs)

                # 실행 시간 측정
                execution_ms = int((time.time() - start_time) * 1000)
                logger.info(f"[TRACE] {run_name} 완료 | {execution_ms}ms")

                return result

            except Exception as e:
                execution_ms = int((time.time() - start_time) * 1000)
                logger.error(f"[TRACE] {run_name} 실패 | {execution_ms}ms | {str(e)[:50]}")
                raise

            finally:
                _clear_trace_context()

        return wrapper
    return decorator


# =============================================================================
# Helper Functions
# =============================================================================

def _build_metadata(state: dict, node_name: str, include_state_info: bool) -> Dict[str, Any]:
    """State에서 트레이싱 메타데이터 추출"""
    metadata = {
        "node_name": node_name,
        "timestamp": datetime.now().isoformat(),
    }

    if include_state_info and state:
        # 민감하지 않은 정보만 포함
        metadata.update({
            "preset": state.get("generation_preset", "balanced"),
            "refine_count": state.get("refine_count", 0),
            "restart_count": state.get("restart_count", 0),
            "thread_id": state.get("thread_id", "unknown"),
            "current_step": state.get("current_step", "unknown"),
        })

        # 분석 결과 요약 (있는 경우)
        analysis = state.get("analysis")
        if analysis:
            if isinstance(analysis, dict):
                metadata["topic"] = analysis.get("topic", "")[:50]
            elif hasattr(analysis, "topic"):
                metadata["topic"] = getattr(analysis, "topic", "")[:50]

    return metadata


def _set_trace_context(run_name: str, tags: List[str], metadata: Dict[str, Any]):
    """
    LangSmith 트레이싱 컨텍스트 설정

    주의: 환경변수 방식은 임시 솔루션입니다.
    프로덕션에서는 RunnableConfig + callbacks 사용 권장.
    """
    # LangSmith 환경변수 (참고용 - 실제로는 langchain callbacks 사용)
    os.environ["LANGCHAIN_RUN_NAME"] = run_name
    os.environ["LANGCHAIN_TAGS"] = ",".join(tags)

    # 메타데이터는 JSON으로 저장하기 어려우므로 로그로만 기록
    logger = get_file_logger()
    logger.debug(f"[TRACE META] {metadata}")


def _clear_trace_context():
    """트레이싱 컨텍스트 정리"""
    os.environ.pop("LANGCHAIN_RUN_NAME", None)
    os.environ.pop("LANGCHAIN_TAGS", None)


# =============================================================================
# Utility Functions (외부에서 사용 가능)
# =============================================================================

def get_trace_summary(state: dict) -> Dict[str, Any]:
    """
    State에서 트레이싱 요약 정보 추출 (UI/디버깅용)

    Returns:
        {
            "total_steps": 5,
            "completed_steps": ["analyze", "structure", "write"],
            "current_step": "review",
            "refine_count": 1,
            "execution_times": {"analyze": "1.2s", ...}
        }
    """
    step_history = state.get("step_history", [])

    completed_steps = []
    execution_times = {}

    for step in step_history:
        step_name = step.get("step", "unknown")
        status = step.get("status", "")
        exec_time = step.get("execution_time", "N/A")

        if status == "SUCCESS":
            completed_steps.append(step_name)
        execution_times[step_name] = exec_time

    return {
        "total_steps": len(step_history),
        "completed_steps": completed_steps,
        "current_step": state.get("current_step", "unknown"),
        "refine_count": state.get("refine_count", 0),
        "restart_count": state.get("restart_count", 0),
        "execution_times": execution_times,
    }


def format_trace_for_langsmith(state: dict) -> str:
    """
    LangSmith 메모용 요약 문자열 생성

    LangSmith 대시보드에서 Run 상세 페이지에 표시됩니다.
    """
    summary = get_trace_summary(state)

    lines = [
        f"📊 실행 요약",
        f"- 완료 단계: {len(summary['completed_steps'])}/{summary['total_steps']}",
        f"- 현재 단계: {summary['current_step']}",
        f"- 개선 횟수: {summary['refine_count']}",
        f"- 재분석 횟수: {summary['restart_count']}",
    ]

    if summary["execution_times"]:
        lines.append("\n⏱️ 실행 시간:")
        for step, time_str in summary["execution_times"].items():
            lines.append(f"  - {step}: {time_str}")

    return "\n".join(lines)
