"""
UI Session Manager

Streamlit 세션 상태(Session State) 초기화 및 관리를 담당합니다.
ui/layout.py에서 분리되어 순환 참조 문제를 방지합니다.
"""
import streamlit as st
import uuid

def init_session_state():
    """
    세션 상태 초기화
    
    앱 실행 시 최초 1회 필요한 세션 변수들을 초기화합니다.
    """
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "plan_history" not in st.session_state:
        st.session_state.plan_history = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    if "current_state" not in st.session_state:
        st.session_state.current_state = None
    if "generated_plan" not in st.session_state:
        st.session_state.generated_plan = None
    if "processing" not in st.session_state:
        st.session_state.processing = False
    if "uploaded_content" not in st.session_state:
        st.session_state.uploaded_content = None
    if "pending_input" not in st.session_state:
        st.session_state.pending_input = None
    if "input_key" not in st.session_state:
        st.session_state.input_key = 0
    if "prefill_prompt" not in st.session_state:
        st.session_state.prefill_prompt = None
    if "trigger_notification" not in st.session_state:
        st.session_state.trigger_notification = False
    if "generation_preset" not in st.session_state:
        st.session_state.generation_preset = "balanced"
    
    # 파일 업로드 관련 상태 (ChatGPT 스타일 UI)
    if "attached_files" not in st.session_state:
        st.session_state.attached_files = []
    if "show_upload_panel" not in st.session_state:
        st.session_state.show_upload_panel = False
    # [NEW] 아이디어 카테고리
    if "idea_category" not in st.session_state:
        st.session_state.idea_category = "random"
