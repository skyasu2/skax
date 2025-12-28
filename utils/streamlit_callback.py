from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
import streamlit as st

class StreamlitStatusCallback(BaseCallbackHandler):
    """
    LangChain/LangGraph 실행 과정을 Streamlit의 st.status 컨테이너에 
    '한 줄'로 깔끔하게 업데이트하며 출력하는 콜백 핸들러입니다.
    """
    def __init__(self, status_container):
        self.status = status_container
        # 로그가 쌓이지 않고 교체되도록 empty 컨테이너 사용
        self.placeholder = self.status.empty()

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        """LLM 생성 시작 시"""
        msg = "🧠 AI가 내용을 생성하고 있습니다..."
        self.status.update(label=msg, state="running")
        self.placeholder.markdown(msg)

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        """도구(Tool) 실행 시작 시"""
        tool_name = serialized.get("name", "Unknown Tool")
        
        icon = "🔧"
        if "search" in tool_name.lower():
            icon = "🌐"
        elif "read" in tool_name.lower():
            icon = "📖"
            
        msg = f"{icon} **{tool_name}** 도구를 사용 중입니다..."
        self.status.update(label=msg, state="running")
        self.placeholder.markdown(f"{msg}\n\nRunning: `{input_str[:100]}...`")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """도구 실행 완료 시"""
        # 완료 메시지는 굳이 표시 안 하거나, 잠시 보여주고 넘어감
        self.placeholder.markdown("✅ 도구 실행 완료. 다음 단계로 넘어갑니다.")

    def on_agent_action(self, action: Any, **kwargs: Any) -> Any:
        """에이전트가 행동을 결정했을 때"""
        tool = action.tool
        msg = f"🤔 AI가 판단 중: `{tool}` 도구가 필요합니다."
        self.status.update(label=msg, state="running")
        self.placeholder.markdown(msg)

    def custom_log(self, message: str, icon: str = "ℹ️"):
        """사용자 정의 로그 출력 (워크플로우 노드에서 직접 호출용)"""
        full_msg = f"{icon} {message}"
        self.status.update(label=full_msg, state="running")
        self.placeholder.markdown(full_msg)
