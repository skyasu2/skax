import time
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
import streamlit as st

# 토큰당 비용 (USD) - GPT-4o 기준
COST_PER_INPUT_TOKEN = 2.5 / 1_000_000  # $2.5 per 1M tokens
COST_PER_OUTPUT_TOKEN = 10 / 1_000_000  # $10 per 1M tokens


class StreamlitStatusCallback(BaseCallbackHandler):
    """
    LangChain/LangGraph 실행 과정을 Streamlit의 st.status 컨테이너에 
    업데이트하며 경과 시간과 진행률을 보여주는 콜백 핸들러입니다.
    
    [NEW] 토큰 사용량 및 예상 비용도 추적합니다.
    """
    def __init__(self, status_container):
        self.status = status_container
        # 로그가 쌓이지 않고 교체되도록 empty 컨테이너 사용
        self.placeholder = self.status.empty()
        self.start_time = time.time()
        self.progress_bar = self.status.progress(0)
        self.current_progress = 0
        
        # [NEW] 토큰 추적
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.llm_call_count = 0

    def _update_ui(self, message: str):
        """UI 업데이트 (메시지 + 경과 시간 + 프로그레스)"""
        elapsed = int(time.time() - self.start_time)
        label_msg = f"{message} ({elapsed}초 경과)"
        self.status.update(label=label_msg, state="running")
        self.placeholder.markdown("---")
        self.placeholder.markdown(f"⏱️ **{elapsed}s**: {message}")

    def _increment_progress(self, amount: int):
        """진행률 증가 (최대 95%까지)"""
        self.current_progress = min(95, self.current_progress + amount)
        self.progress_bar.progress(self.current_progress / 100)

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """LLM 생성 시작 시"""
        self._increment_progress(10) # LLM은 무거운 작업이므로 크게 증가
        self._update_ui("🧠 AI가 기획 내용을 생성/분석하고 있습니다...")
        self.llm_call_count += 1

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 생성 완료 시 - 토큰 사용량 추적"""
        try:
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                self.total_input_tokens += usage.get("prompt_tokens", 0)
                self.total_output_tokens += usage.get("completion_tokens", 0)
        except Exception:
            pass  # 토큰 정보가 없어도 무시

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """도구(Tool) 실행 시작 시"""
        tool_name = serialized.get("name", "Unknown Tool")
        self._increment_progress(5)
        
        icon = "🔧"
        if "search" in tool_name.lower():
            icon = "🌐"
        elif "read" in tool_name.lower():
            icon = "📖"
            
        msg = f"{icon} **{tool_name}** 도구를 사용 중입니다..."
        self._update_ui(msg)

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        """에이전트가 행동을 결정했을 때"""
        tool = action.tool
        self._update_ui(f"🤔 AI 판단: `{tool}` 도구 호출")

    def custom_log(self, message: str, icon: str = "ℹ️"):
        """사용자 정의 로그 출력"""
        self._increment_progress(5)
        full_msg = f"{icon} {message}"
        self._update_ui(full_msg)
    
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
            "estimated_cost_krw": round(estimated_cost * 1350, 0)  # 환율 가정
        }

