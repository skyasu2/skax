"""
PlanCraft Agent - Main Application

AI 기반 기획서 자동 생성 서비스입니다.
LangGraph 워크플로우와 Azure OpenAI를 활용합니다.
"""

import streamlit as st
import os
import sys
import uuid
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config import Config

# UI 컴포넌트 Import (분리된 모듈에서)
from ui import (
    render_chat_message,
    show_plan_dialog,
    show_analysis_dialog,
    show_history_dialog,
    render_dev_tools,
    render_refinement_ui,
    render_error_state,
    render_visual_timeline,
    render_human_interaction
)

# =============================================================================
# 페이지 설정
# =============================================================================
st.set_page_config(
    page_title="PlanCraft Agent",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================================================================
# CSS 스타일
# =============================================================================
from ui.styles import CUSTOM_CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# 세션 상태 초기화
# =============================================================================
def init_session_state():
    """세션 상태 초기화"""
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


# =============================================================================
# 리소스 초기화 (RAG, Config 등)
# =============================================================================
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
        start_api_server(port=8000)
        print("[INIT] FastAPI Backend Server Started on http://127.0.0.1:8000")

        # 1. Config 검증
        Config.validate()

        # 2. RAG 벡터스토어 로드
        from rag.vectorstore import load_vectorstore
        print("[INIT] Loading RAG Vectorstore...")
        load_vectorstore()

    except Exception as e:
        print(f"[WARN] Resource Initialization Warning: {e}")


# =============================================================================
# 헤더 렌더링
# =============================================================================
def _render_header():
    """헤더 영역 렌더링 (타이틀, 프리셋, 메뉴)"""
    # 알림 트리거 확인
    if st.session_state.get("trigger_notification"):
        from ui.components import trigger_browser_notification
        trigger_browser_notification("PlanCraft 알림", "기획서 작성이 완료되었습니다! 📄")
        st.session_state.trigger_notification = False

    col_title, col_preset, col_menu = st.columns([4, 2.5, 0.5])

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")

    with col_preset:
        from utils.settings import GENERATION_PRESETS
        preset_keys = list(GENERATION_PRESETS.keys())
        st.selectbox(
            "생성 모드",
            options=preset_keys,
            format_func=lambda k: f"{GENERATION_PRESETS[k].icon} {GENERATION_PRESETS[k].name} ({GENERATION_PRESETS[k].description})",
            key="generation_preset",
            label_visibility="collapsed",
            help="⚡빠른(GPT-4o-mini): 속도/가성비 | ⚖️균형(GPT-4o): 표준 | 💎고품질(GPT-4o+Deep): 심층분석"
        )

    with col_menu:
        with st.popover("☰"):
            st.caption("PlanCraft v2.1")

            if st.button("🆕 새 대화 시작", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.current_state = None
                st.session_state.generated_plan = None
                st.session_state.input_key += 1
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.idea_category = "random"
                st.session_state.idea_llm_count = 0
                st.session_state.random_examples = None
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


# =============================================================================
# 브레인스토밍 히어로 렌더링
# =============================================================================
def _render_brainstorming_hero():
    """시작 화면 브레인스토밍 UI"""
    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

    # 세션 상태 초기화
    if "idea_category" not in st.session_state:
        st.session_state.idea_category = "random"
    if "idea_llm_count" not in st.session_state:
        st.session_state.idea_llm_count = 0
    if "random_examples" not in st.session_state or st.session_state.random_examples is None:
        from utils.prompt_examples import get_examples_by_category
        st.session_state.random_examples = get_examples_by_category("random", 3)

    from utils.prompt_examples import CATEGORIES, get_examples_by_category
    cat_keys = list(CATEGORIES.keys())

    def on_category_change():
        new_category = st.session_state.idea_category
        st.session_state.random_examples = get_examples_by_category(new_category, 3)

    llm_remaining = max(0, 10 - st.session_state.idea_llm_count)
    col_title, col_dropdown, col_btn = st.columns([2.5, 1.5, 1])

    with col_title:
        st.markdown(f"#### 🎲 AI 브레인스토밍 <small style='color:gray;'>({llm_remaining}회)</small>", unsafe_allow_html=True)

    with col_dropdown:
        st.selectbox(
            "카테고리",
            options=cat_keys,
            format_func=lambda k: f"{CATEGORIES[k]['icon']} {CATEGORIES[k]['label']}",
            key="idea_category",
            label_visibility="collapsed",
            on_change=on_category_change
        )

    with col_btn:
        if st.button("🔄 AI 생성", key="refresh_hero_ex", use_container_width=True, help="AI가 실시간으로 새로운 아이디어를 제안합니다"):
            from utils.idea_generator import generate_ideas
            with st.spinner("💡 아이디어를 떠올리는 중..."):
                ideas, used_llm = generate_ideas(
                    category=st.session_state.idea_category,
                    count=3,
                    use_llm=True,
                    session_call_count=st.session_state.idea_llm_count
                )
                st.session_state.random_examples = ideas
                if used_llm:
                    st.session_state.idea_llm_count += 1
            st.rerun()

    current_cat = CATEGORIES.get(st.session_state.idea_category, {})
    st.caption(f"💡 {current_cat.get('description', '')}")

    cols = st.columns(3)
    for i, (title, prompt) in enumerate(st.session_state.random_examples):
        with cols[i]:
            if st.button(title, key=f"hero_ex_{i}", use_container_width=True, help=prompt):
                st.session_state.prefill_prompt = prompt

    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-left: 4px solid #667eea;
        border-radius: 8px;
        padding: 12px 16px;
        margin-top: 1rem;
    ">
        <strong>💡 Tip: 빠른 기획서 생성을 위한 입력 가이드</strong>
        <p style="margin: 8px 0 0 0; color: #495057; font-size: 0.9rem;">
            <b>20자 이상</b> 입력 시 확인 절차 없이 바로 기획서가 생성됩니다.<br/>
            예) "직장인을 위한 AI 기반 식단 관리 앱" ✅ &nbsp; vs &nbsp; "다이어트 앱" ❓ (확인 필요)
        </p>
    </div>
    """, unsafe_allow_html=True)


# =============================================================================
# 채팅 히스토리 & 상태 렌더링
# =============================================================================
def _render_chat_and_state():
    """채팅 히스토리와 현재 상태 UI 렌더링"""
    # 채팅 히스토리
    for msg in st.session_state.chat_history:
        render_chat_message(msg["role"], msg["content"], msg.get("type", "text"))

    # 현재 상태 기반 UI
    if st.session_state.current_state:
        state = st.session_state.current_state

        if state.get("error") or state.get("error_message"):
            render_error_state(state)

        elif state.get("__interrupt__"):
            payload = state["__interrupt__"]
            ui_state = state.copy()
            ui_state.update({
                "input_schema_name": payload.get("input_schema_name"),
                "options": payload.get("options"),
                "option_question": payload.get("question"),
                "error": payload.get("error"),
                "need_more_info": True
            })
            render_human_interaction(ui_state)

        elif state.get("need_more_info"):
            render_human_interaction(state)

        elif state.get("final_output") and not state.get("analysis", {}).get("is_general_query", False):
            st.success("기획서 작성이 완료되었습니다!")
            st.session_state.generated_plan = state["final_output"]

            if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != state["final_output"]:
                now_str = datetime.now().strftime("%H:%M:%S")
                st.session_state.plan_history.append({
                    "version": len(st.session_state.plan_history) + 1,
                    "timestamp": now_str,
                    "content": state["final_output"]
                })

            st.divider()
            col_act1, col_act2 = st.columns(2)
            with col_act1:
                st.markdown('<div class="bounce-guide">👇 클릭하여 확인</div>', unsafe_allow_html=True)
                if st.button("📄 기획서 보기", type="primary", use_container_width=True):
                    show_plan_dialog()
            with col_act2:
                if st.button("🔍 AI 분석 데이터 (설계도)", use_container_width=True):
                    show_analysis_dialog()

            with st.expander("📊 실행 과정 상세 보기", expanded=False):
                hist = state.get("step_history", [])
                render_visual_timeline(hist)

            render_refinement_ui()


# =============================================================================
# 파일 업로드 렌더링
# =============================================================================
def _render_file_upload():
    """파일 업로드 영역 렌더링"""
    with st.expander("📎 참고 자료 추가 (파일 업로드)", expanded=False):
        MAX_FILE_SIZE_MB = 10
        MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
        ALLOWED_EXTENSIONS = {"txt", "md", "docx", "pdf"}

        uploaded_file = st.file_uploader(
            "기획서 생성에 참고할 파일 (PDF, DOCX, TXT 등)",
            type=["txt", "md", "docx", "pdf"],
            key="file_uploader_bottom"
        )
        if uploaded_file:
            try:
                file_size = len(uploaded_file.getbuffer())
                if file_size > MAX_FILE_SIZE_BYTES:
                    st.error(f"파일이 너무 큽니다. 최대 {MAX_FILE_SIZE_MB}MB까지 허용됩니다.")
                elif ".." in uploaded_file.name or "/" in uploaded_file.name or "\\" in uploaded_file.name:
                    st.error("유효하지 않은 파일명입니다.")
                elif not uploaded_file.name.split(".")[-1].lower() in ALLOWED_EXTENSIONS:
                    st.error("지원하지 않는 파일 형식입니다.")
                else:
                    content = uploaded_file.read().decode("utf-8", errors='ignore')
                    if len(content) > 50000:
                        content = content[:50000]
                        st.warning("파일이 너무 길어 일부만 사용됩니다 (50,000자 제한)")
                    st.session_state.uploaded_content = content
                    st.success(f"✅ '{uploaded_file.name}' 업로드됨 ({file_size // 1024}KB)")
            except Exception as e:
                st.error("파일을 읽을 수 없습니다. 파일 형식을 확인해주세요.")


# =============================================================================
# 입력 영역 렌더링
# =============================================================================
def _render_input_area():
    """채팅 입력 영역 렌더링. status_placeholder 반환."""
    # Prefill 확인 UI
    if st.session_state.prefill_prompt and not st.session_state.pending_input:
        st.info(f"📝 **선택된 예시:** {st.session_state.prefill_prompt}")
        col_ok, col_no = st.columns([1, 1])
        with col_ok:
            if st.button("✅ 이대로 시작", use_container_width=True):
                user_msg = st.session_state.prefill_prompt
                st.session_state.prefill_prompt = None
                st.session_state.chat_history.append({"role": "user", "content": user_msg, "type": "text"})
                st.session_state.pending_input = user_msg
                st.rerun()
        with col_no:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.prefill_prompt = None
                st.rerun()

    # 상태 표시기 Placeholder
    st.markdown("<div style='margin-bottom: 0.5rem;'></div>", unsafe_allow_html=True)
    status_placeholder = st.empty()

    # 채팅 입력창
    placeholder_text = "💬 자유롭게 대화를 입력하세요..."
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        placeholder_text = "💬 위 옵션을 선택하거나, 다른 의견을 직접 입력하세요..."

    user_input = st.chat_input(placeholder_text, key=f"chat_input_{st.session_state.input_key}")

    if user_input:
        st.session_state.prefill_prompt = None
        st.session_state.chat_history.append({"role": "user", "content": user_input, "type": "text"})
        st.session_state.input_key += 1
        st.session_state.pending_input = user_input
        st.rerun()

    return status_placeholder


# =============================================================================
# 메인 렌더링 (리팩토링됨)
# =============================================================================
def render_main():
    """메인 영역 렌더링 (분리된 컴포넌트 조합)"""
    # 1. 헤더
    _render_header()

    # 2. 시작 화면 (채팅 히스토리가 없을 때만)
    if not st.session_state.chat_history:
        _render_brainstorming_hero()

    # 3. 채팅 히스토리 & 현재 상태
    _render_chat_and_state()

    # 4. 하단 입력 영역
    st.markdown("---")
    _render_file_upload()
    status_placeholder = _render_input_area()

    # 5. 워크플로우 실행 (분리된 모듈)
    if st.session_state.pending_input:
        pending_text = st.session_state.pending_input
        st.session_state.pending_input = None

        from ui.workflow_runner import run_pending_workflow
        run_pending_workflow(pending_text, status_placeholder)


# =============================================================================
# 메인 함수
# =============================================================================
def main():
    """메인 함수"""
    # 1. 리소스 초기화
    init_resources()

    # 2. 세션 초기화
    init_session_state()

    # 3. 메인 UI 렌더링
    render_main()


if __name__ == "__main__":
    main()
