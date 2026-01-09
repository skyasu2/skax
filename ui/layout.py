"""
UI Layout & Initialization
"""
import streamlit as st
import uuid
import os
import sys
from utils.config import Config
from utils.runtime import RuntimeContext

# Top-level imports removed to prevent circular dependencies
# from ui.dialogs import show_history_dialog, render_dev_tools 

@st.cache_resource
def init_resources():
    """
    앱 실행 시 무거운 리소스를 초기화합니다.
    st.cache_resource를 사용하여 프로세스당 1회만 실행되도록 합니다.
    """
    try:
        # 0. FastAPI 백엔드 서버 시작 (Thread)
        from api.main import start_api_server
        print("[INIT] Starting FastAPI Backend Server...")
        actual_port = start_api_server(start_port=8000)
        
        # [Update Config] RuntimeContext를 통해 안전하게 업데이트
        runtime = RuntimeContext.get_instance()
        runtime.set_api_port(actual_port)
        
        print(f"[INIT] FastAPI Backend Server Started at {runtime.api_base_url}")

        # 1. Config 검증
        Config.validate()

        # 2. RAG 벡터스토어 로드 (Background)
        import threading
        def _init_rag_bg():
            from rag.vectorstore import load_vectorstore, rebuild_index_if_needed
            print("[INIT] Checking RAG Vectorstore...")
            # 없거나 깨졌을 때만 재생성
            rebuild_index_if_needed()
            load_vectorstore()
            print("[INIT] RAG Vectorstore Ready")

        rag_thread = threading.Thread(target=_init_rag_bg, daemon=True)
        rag_thread.start()

        return actual_port

    except Exception as e:
        print(f"[WARN] Resource Initialization Warning: {e}")
        return 8000 # Default fallback


def render_header():
    """헤더 영역 렌더링 (타이틀, 프리셋, 메뉴)"""
    # [Lazy Import] 순환 참조 방지
    from ui.components import trigger_browser_notification
    from ui.dialogs import show_history_dialog, render_dev_tools
    from ui.session import init_session_state # 필요한 경우

    # 알림 트리거 확인
    if st.session_state.get("trigger_notification"):
        trigger_browser_notification("PlanCraft 알림", "기획서 작성이 완료되었습니다! 📄")
        st.session_state.trigger_notification = False

    col_title, col_blank, col_menu = st.columns([6, 1, 0.5])

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")

    with col_menu:
        with st.popover("☰"):
            st.caption("PlanCraft v2.1")

            if st.button("🆕 새 대화 시작", use_container_width=True):
                # 세션 초기화 동작
                st.session_state.chat_history = []
                st.session_state.current_state = None
                st.session_state.generated_plan = None
                st.session_state.input_key += 1
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.idea_category = "random"
                # 기타 상태 초기화가 필요할 수 있음
                st.rerun()

            if st.button("📜 대화 히스토리", use_container_width=True):
                show_history_dialog()

            st.divider()

            if st.button("🛠 개발자 도구 (Dev)", use_container_width=True):
                render_dev_tools()

            with st.expander("⚙️ 설정 / 상태"):
                try:
                    Config.validate()
                    st.success("Cloud: Azure OpenAI ✅")
                except EnvironmentError:
                    st.error("Cloud: Disconnected ❌")
                st.caption("Pipeline: Analyzer → Structurer → Writer")

    st.divider()
