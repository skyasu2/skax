import time
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# 토큰당 비용 (USD) - GPT-4o 기준
COST_PER_INPUT_TOKEN = 2.5 / 1_000_000  # $2.5 per 1M tokens
COST_PER_OUTPUT_TOKEN = 10 / 1_000_000  # $10 per 1M tokens


class TokenTrackingCallback(BaseCallbackHandler):
    """
    API 환경에서 토큰 사용량을 추적하는 콜백.
    Streamlit 의존성 없이 토큰 사용량만 추적합니다.
    """

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.llm_call_count = 0

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """LLM 호출 시작"""
        self.llm_call_count += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 호출 완료 - 토큰 추적"""
        try:
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                self.total_input_tokens += usage.get("prompt_tokens", 0)
                self.total_output_tokens += usage.get("completion_tokens", 0)
        except Exception:
            pass

    def get_usage_summary(self) -> dict:
        """토큰 사용량 요약"""
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

# 단계별 표시 정보 (key, icon, label, progress%)
STEP_INFO = {
    "context": ("📚", "컨텍스트 수집", 10),
    "analyze": ("🔍", "요구사항 분석", 20),
    "structure": ("🏗️", "구조 설계", 35),
    "write": ("✍️", "콘텐츠 작성", 55),
    "review": ("📋", "품질 검토", 70),
    "discuss": ("💬", "에이전트 토론", 75),
    "refine": ("🔧", "내용 개선", 85),
    "format": ("📄", "최종 포맷팅", 95),
}


class StreamlitStatusCallback(BaseCallbackHandler):
    """
    LangChain/LangGraph 실행 과정을 Streamlit st.status에 실시간 표시.

    st.status 특성:
    - status.update(label=...) → 실시간 반영 ✅
    - status.progress() → 실시간 반영 ✅
    - 내부 markdown/write → 완료 후에만 표시 ❌

    따라서 label과 progress만 실시간 업데이트합니다.
    """

    def __init__(self, status_container):
        self.status = status_container
        self.start_time = time.time()

        # 진행률 바
        self.progress_bar = self.status.progress(0)

        # 실행 기록 (완료 후 표시용)
        self.execution_log: List[tuple] = []
        self.current_step_key: Optional[str] = None
        self.step_start_time: Optional[float] = None

        # 토큰 추적
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.llm_call_count = 0

    def set_step(self, step_key: str):
        """현재 단계 설정 - label과 progress 실시간 업데이트"""
        # 이전 단계 완료 기록
        if self.current_step_key and self.step_start_time:
            elapsed = round(time.time() - self.step_start_time, 1)
            self.execution_log.append((self.current_step_key, elapsed))

        # 새 단계 시작
        self.current_step_key = step_key
        self.step_start_time = time.time()

        # 단계 정보 가져오기
        info = STEP_INFO.get(step_key)
        if info:
            icon, label, progress = info
            total_elapsed = int(time.time() - self.start_time)

            # ✅ 실시간 반영되는 업데이트
            self.status.update(
                label=f"{icon} {label} ({total_elapsed}초 경과)",
                state="running"
            )
            self.progress_bar.progress(progress / 100)

    def finish(self):
        """완료 처리 - 최종 로그 표시"""
        # 마지막 단계 기록
        if self.current_step_key and self.step_start_time:
            elapsed = round(time.time() - self.step_start_time, 1)
            self.execution_log.append((self.current_step_key, elapsed))
            self.current_step_key = None

        total_elapsed = int(time.time() - self.start_time)

        # 진행률 100%
        self.progress_bar.progress(100)

        # 완료 후 실행 로그 표시 (이제 표시됨)
        if self.execution_log:
            log_text = "**실행 완료:**\n\n"
            for step_key, elapsed in self.execution_log:
                info = STEP_INFO.get(step_key, ("▶️", step_key, 0))
                icon, label, _ = info
                log_text += f"✅ {icon} {label} - {elapsed}s\n\n"
            self.status.markdown(log_text)

        # 완료 상태
        self.status.update(
            label=f"✅ 완료! (총 {total_elapsed}초)",
            state="complete"
        )

    # =========================================================================
    # LangChain 콜백 메서드
    # =========================================================================

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """LLM 호출 시작"""
        self.llm_call_count += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 호출 완료 - 토큰 추적"""
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
        pass

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        pass

    def custom_log(self, message: str, icon: str = "ℹ️"):
        """하위 호환용"""
        pass

    def get_usage_summary(self) -> dict:
        """토큰 사용량 요약"""
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
        """실행 로그 요약"""
        return [
            {"step": step, "elapsed": elapsed}
            for step, elapsed in self.execution_log
        ]
