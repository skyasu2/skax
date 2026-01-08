"""
Input & Controls Tab - 채팅 입력창 UI
"""
import streamlit as st


# =============================================================================
# 아이콘 버튼 스타일 (CSS)
# =============================================================================
ICON_BUTTON_CSS = """
<style>
/* 아이콘 버튼 컨테이너 */
.icon-btn-container {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 0;
}

/* 개별 아이콘 버튼 */
.icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 16px;
    border: none;
    background: transparent;
}
.icon-btn:hover {
    background: rgba(128, 128, 128, 0.2);
}
.icon-btn.active {
    background: rgba(59, 130, 246, 0.2);
    color: #3b82f6;
}

/* 모드 선택 아이콘 그룹 */
.mode-icons {
    display: flex;
    gap: 2px;
    margin-left: 8px;
    padding-left: 8px;
    border-left: 1px solid rgba(128, 128, 128, 0.3);
}

/* 업로드된 파일 표시 */
.uploaded-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    background: rgba(34, 197, 94, 0.15);
    border-radius: 12px;
    font-size: 12px;
    color: #22c55e;
}
</style>
"""


def render_file_upload():
    """파일 업로드 영역 렌더링 (팝오버 스타일)"""
    MAX_FILE_SIZE_MB = 10
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {"txt", "md", "docx", "pdf"}

    uploaded_file = st.file_uploader(
        "📎 참고 자료 (PDF, DOCX, TXT, MD)",
        type=["txt", "md", "docx", "pdf"],
        key="file_uploader_bottom",
        label_visibility="collapsed"
    )
    if uploaded_file:
        try:
            file_size = len(uploaded_file.getbuffer())
            if file_size > MAX_FILE_SIZE_BYTES:
                st.error(f"파일이 너무 큽니다. 최대 {MAX_FILE_SIZE_MB}MB까지 허용됩니다.")
            elif ".." in uploaded_file.name or "/" in uploaded_file.name or "\\" in uploaded_file.name:
                st.error("유효하지 않은 파일명입니다.")
            elif uploaded_file.name.split(".")[-1].lower() not in ALLOWED_EXTENSIONS:
                st.error("지원하지 않는 파일 형식입니다.")
            else:
                content = uploaded_file.read().decode("utf-8", errors='ignore')
                if len(content) > 50000:
                    content = content[:50000]
                    st.warning("파일이 너무 길어 일부만 사용됩니다 (50,000자 제한)")
                st.session_state.uploaded_content = content
                st.success(f"✅ '{uploaded_file.name}' ({file_size // 1024}KB)")
        except Exception:
            st.error("파일을 읽을 수 없습니다.")


def render_input_area():
    """채팅 입력 영역 렌더링. status_placeholder 반환."""
    # CSS 스타일 적용
    st.markdown(ICON_BUTTON_CSS, unsafe_allow_html=True)

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

    # ==========================================================================
    # [NEW] 아이콘 기반 입력 컨트롤 (+ 버튼, 파일, 모드 선택)
    # ==========================================================================

    # 세션 상태 초기화
    if "show_file_upload" not in st.session_state:
        st.session_state.show_file_upload = False

    # 모드 설정 (아이콘-모드 매핑)
    MODE_CONFIG = {
        "speed": {"icon": "⚡", "label": "속도", "desc": "빠른 응답"},
        "balanced": {"icon": "⚖️", "label": "균형", "desc": "속도+품질"},
        "quality": {"icon": "💎", "label": "고품질", "desc": "깊은 분석"},
    }

    # 아이콘 버튼 행
    col_plus, col_file_status, col_spacer, col_mode1, col_mode2, col_mode3 = st.columns([0.5, 2, 4, 0.6, 0.6, 0.6])

    with col_plus:
        # + 버튼 (파일 업로드 토글)
        if st.button("➕", key="btn_plus", help="파일 첨부"):
            st.session_state.show_file_upload = not st.session_state.show_file_upload
            st.rerun()

    with col_file_status:
        # 업로드된 파일 표시
        if st.session_state.get("uploaded_content"):
            st.markdown(
                '<span class="uploaded-badge">📎 파일 첨부됨</span>',
                unsafe_allow_html=True
            )

    # 모드 선택 아이콘 버튼들
    current_mode = st.session_state.generation_preset
    modes = ["speed", "balanced", "quality"]
    mode_cols = [col_mode1, col_mode2, col_mode3]

    for mode, col in zip(modes, mode_cols):
        config = MODE_CONFIG[mode]
        with col:
            is_active = mode == current_mode
            btn_type = "primary" if is_active else "secondary"
            if st.button(
                config["icon"],
                key=f"mode_{mode}",
                type=btn_type,
                help=f"{config['label']}: {config['desc']}"
            ):
                st.session_state.generation_preset = mode
                st.rerun()

    # 파일 업로드 영역 (토글)
    if st.session_state.show_file_upload:
        with st.container():
            render_file_upload()

    # 채팅 입력창
    placeholder_text = "💬 자유롭게 대화를 입력하세요..."
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        placeholder_text = "💬 위 옵션을 선택하거나, 다른 의견을 직접 입력하세요..."

    user_input = st.chat_input(placeholder_text, key=f"chat_input_{st.session_state.input_key}")

    # [NEW] 채팅 입력창 자동 포커스 (JavaScript via components.html)
    import streamlit.components.v1 as components
    components.html("""
    <script>
    const focusChatInput = () => {
        const input = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (input) {
            input.focus();
        } else {
            setTimeout(focusChatInput, 100);
        }
    };
    setTimeout(focusChatInput, 50);
    </script>
    """, height=0)

    if user_input:
        st.session_state.prefill_prompt = None
        st.session_state.chat_history.append({"role": "user", "content": user_input, "type": "text"})
        st.session_state.input_key += 1
        st.session_state.pending_input = user_input

        # [FIX] 새 대화 메시지마다 thread_id 갱신 (이전 상태 오염 방지)
        # Resume(HITL 응답)이 아닌 새 질문일 때만 thread_id 갱신
        if not st.session_state.current_state or not st.session_state.current_state.get("need_more_info"):
            import uuid
            st.session_state.thread_id = str(uuid.uuid4())

        st.rerun()

    return status_placeholder
