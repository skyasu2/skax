"""
Input & Controls Tab
"""
import streamlit as st

def render_file_upload():
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


def render_input_area():
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

    # 채팅 입력창과 모드 선택을 위한 컨테이너 (Streamlit 특성상 chat_input은 하단 고정되므로, 그 위에 옵션 배치)
    col_mode, col_blank = st.columns([2, 8])
    with col_mode:
        preset_mode = st.selectbox(
            "품질 모드 선택",
            ["balanced", "quality", "speed"],
            format_func=lambda x: {
                "balanced": "⚖️ 균형 (Balanced)",
                "quality": "💎 고품질 (High Quality)",
                "speed": "⚡ 속도 (Speed)"
            }[x],
            index=["balanced", "quality", "speed"].index(st.session_state.generation_preset),
            key="preset_selector_main", # Key 변경하여 충돌 방지
            label_visibility="collapsed", # 라벨 숨김으로 공간 절약
            help="**모드 설명**\n\n"
                 "⚖️ **균형**: 속도와 품질의 조화 (기본)\n"
                 "💎 **고품질**: 더 깊이 있는 분석과 상세한 내용 (오래 걸림)\n"
                 "⚡ **속도**: 빠른 응답과 핵심 요약 위주"
        )
        # 선택 변경 시 세션 업데이트
        if preset_mode != st.session_state.generation_preset:
            st.session_state.generation_preset = preset_mode

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

        # [FIX] 새 대화 메시지마다 thread_id 갱신 (이전 상태 오염 방지)
        # Resume(HITL 응답)이 아닌 새 질문일 때만 thread_id 갱신
        if not st.session_state.current_state or not st.session_state.current_state.get("need_more_info"):
            import uuid
            st.session_state.thread_id = str(uuid.uuid4())

        st.rerun()

    return status_placeholder
