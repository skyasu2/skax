import time
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
import streamlit as st

# 토큰당 비용 (USD) - GPT-4o 기준
COST_PER_INPUT_TOKEN = 2.5 / 1_000_000  # $2.5 per 1M tokens
COST_PER_OUTPUT_TOKEN = 10 / 1_000_000  # $10 per 1M tokens

# 단계별 표시 정보
STEP_INFO = {
    "context": ("📚", "컨텍스트 수집"),
    "analyze": ("🔍", "요구사항 분석"),
    "structure": ("🏗️", "구조 설계"),
    "write": ("✍️", "콘텐츠 작성"),
    "review": ("📋", "품질 검토"),
    "discuss": ("💬", "에이전트 토론"),
    "refine": ("🔧", "내용 개선"),
    "format": ("📄", "최종 포맷팅"),
}


class StreamlitStatusCallback(BaseCallbackHandler):
    """
    LangChain/LangGraph 실행 과정을 Streamlit에 실시간으로 표시합니다.

    [동적 로그 방식]
    - 실제 실행된 노드를 순서대로 표시
    - 루프 실행 시 같은 단계가 여러 번 표시됨
    - 현재 진행 중인 단계 하이라이트
    """

    def __init__(self, status_container):
        self.status = status_container
        self.start_time = time.time()

        # 실행 로그 저장: [(step_key, elapsed_time, extra_info), ...]
        self.execution_log: List[tuple] = []
        self.current_step_key: Optional[str] = None
        self.step_start_time: Optional[float] = None

        # UI 컨테이너
        self.log_container = self.status.container()
        self.progress_bar = self.status.progress(0)
        self.current_progress = 0

        # 토큰 추적
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.llm_call_count = 0

    def _render_log(self):
        """실행 로그 UI 렌더링"""
        self.log_container.empty()

        with self.log_container:
            # 완료된 단계들
            for step_key, elapsed, extra_info in self.execution_log:
                icon, label = STEP_INFO.get(step_key, ("▶️", step_key))
                extra_str = f" ({extra_info})" if extra_info else ""
                st.markdown(f"✅ {icon} **{label}** - {elapsed}s{extra_str}")

            # 현재 진행 중인 단계
            if self.current_step_key:
                icon, label = STEP_INFO.get(self.current_step_key, ("▶️", self.current_step_key))
                elapsed = round(time.time() - (self.step_start_time or self.start_time), 1)
                st.markdown(f"⏳ {icon} **{label}** - {elapsed}s ...")

    def set_step(self, step_key: str, extra_info: str = ""):
        """
        현재 단계 설정 및 로그 업데이트

        Args:
            step_key: 단계 키 (context, analyze, structure, write, review, refine, format)
            extra_info: 추가 정보 (예: "점수: 7점", "2회차")
        """
        # 이전 단계 완료 처리
        if self.current_step_key and self.step_start_time:
            elapsed = round(time.time() - self.step_start_time, 1)
            # 이전 단계의 extra_info 가져오기 (있으면)
            prev_extra = ""
            self.execution_log.append((self.current_step_key, elapsed, prev_extra))

        # 새 단계 시작
        self.current_step_key = step_key
        self.step_start_time = time.time()

        # 진행률 업데이트 (로그 개수 기반)
        self.current_progress = min(95, len(self.execution_log) * 12 + 10)
        self.progress_bar.progress(self.current_progress / 100)

        # 상태 라벨 업데이트
        icon, label = STEP_INFO.get(step_key, ("▶️", step_key))
        total_elapsed = int(time.time() - self.start_time)
        self.status.update(label=f"{icon} {label} ({total_elapsed}초 경과)", state="running")

        # UI 렌더링
        self._render_log()

    def add_step_info(self, info: str):
        """현재 단계에 추가 정보 설정 (예: 점수)"""
        # 마지막 로그 항목 업데이트
        if self.execution_log:
            last = self.execution_log[-1]
            self.execution_log[-1] = (last[0], last[1], info)
            self._render_log()

    def finish(self):
        """마지막 단계 완료 처리"""
        if self.current_step_key and self.step_start_time:
            elapsed = round(time.time() - self.step_start_time, 1)
            self.execution_log.append((self.current_step_key, elapsed, ""))
            self.current_step_key = None

        # 완료 상태
        self.progress_bar.progress(100)
        total_elapsed = int(time.time() - self.start_time)
        self.status.update(label=f"✅ 완료! (총 {total_elapsed}초)", state="complete")
        self._render_log()

    def _update_ui(self, message: str):
        """UI 업데이트 (메시지 + 경과 시간)"""
        elapsed = int(time.time() - self.start_time)
        self.status.update(label=f"{message} ({elapsed}초 경과)", state="running")

    def _increment_progress(self, amount: int):
        """진행률 증가 (최대 95%까지)"""
        self.current_progress = min(95, self.current_progress + amount)
        self.progress_bar.progress(self.current_progress / 100)

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """LLM 생성 시작 시"""
        self.llm_call_count += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 생성 완료 시 - 토큰 사용량 추적"""
        try:
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                self.total_input_tokens += usage.get("prompt_tokens", 0)
                self.total_output_tokens += usage.get("completion_tokens", 0)
        except Exception:
            pass

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """도구(Tool) 실행 시작 시"""
        pass

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        """에이전트가 행동을 결정했을 때"""
        pass

    def custom_log(self, message: str, icon: str = "ℹ️"):
        """사용자 정의 로그 출력 (하위 호환)"""
        pass

    def get_usage_summary(self) -> dict:
        """토큰 사용량 및 예상 비용 요약 반환"""
        total_tokens = self.total_input_tokens + self.total_output_tokens
        estimated_cost = (
            self.total_input_tokens * COST_PER_INPUT_TOKEN +
            self.total_output_tokens * COST_PER_OUTPUT_TOKEN
        )

        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": total_tokens,
            "llm_calls": self.llm_call_count,
            "estimated_cost_usd": round(estimated_cost, 4),
            "estimated_cost_krw": round(estimated_cost * 1350, 0)
        }

    def get_execution_summary(self) -> List[dict]:
        """실행 로그 요약 반환"""
        return [
            {"step": step, "elapsed": elapsed, "info": info}
            for step, elapsed, info in self.execution_log
        ]
