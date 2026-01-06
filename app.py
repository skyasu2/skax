"""
PlanCraft Agent - Main Application

AI 기반 기획서 자동 생성 서비스입니다.
LangGraph 워크플로우와 Azure OpenAI를 활용합니다.
"""
import streamlit as st
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.styles import CUSTOM_CSS
from ui.layout import init_session_state, init_resources, render_header
from ui.tabs.hero import render_brainstorming_hero
from ui.tabs.chat_view import render_chat_and_state
from ui.tabs.controls import render_file_upload, render_input_area
from ui.workflow_runner import run_pending_workflow

# 페이지 설정
st.set_page_config(
    page_title="PlanCraft Agent",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일 적용
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def main():
    """메인 함수"""
    # 1. 초기화
    # 1. 초기화
    api_port = init_resources()
    from utils.config import Config
    Config.API_BASE_URL = f"http://127.0.0.1:{api_port}/api/v1"
    
    init_session_state()

    # 2. 헤더
    render_header()

    # 3. 메인 콘텐츠
    if not st.session_state.chat_history:
        render_brainstorming_hero()

    render_chat_and_state()

    # 4. 하단 컨트롤
    st.markdown("---")
    render_file_upload()
    status_placeholder = render_input_area()

    # 5. 워크플로우 실행
    if st.session_state.pending_input:
        pending_text = st.session_state.pending_input
        st.session_state.pending_input = None
        run_pending_workflow(pending_text, status_placeholder)


if __name__ == "__main__":
    main()
