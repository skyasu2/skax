"""
UI Dialog: Analysis & History
"""
import streamlit as st
import datetime

@st.dialog("🔍 AI 분석 데이터 (설계도)", width="large")
def show_analysis_dialog():
    """분석 결과 상세 보기 모달"""
    if not st.session_state.current_state:
        st.warning("분석 결과가 없습니다.")
        return

    state = st.session_state.current_state
    has_content = False

    def safe_dump(data):
        if hasattr(data, "model_dump"):
            return data.model_dump()
        if hasattr(data, "dict"):
            return data.dict()
        return data

    try:
        if state.get("analysis"):
            st.subheader("🔍 입력 분석")
            st.json(safe_dump(state["analysis"]))
            has_content = True

        if state.get("structure"):
            st.subheader("📐 구조 설계")
            st.json(safe_dump(state["structure"]))
            has_content = True

        if state.get("review"):
            st.subheader("📝 검토 결과")
            st.json(safe_dump(state["review"]))
            has_content = True
            
        if not has_content:
            st.info("⚠️ 상세 분석 데이터가 없습니다. (일반 응답이거나 데이터가 유실되었습니다.)")
            with st.expander("디버깅용 전체 상태 확인 (Raw)", expanded=False):
                st.json(safe_dump(state))
                
    except Exception as e:
        st.error(f"데이터 렌더링 중 오류가 발생했습니다: {str(e)}")
        with st.expander("상세 에러", expanded=False):
            st.write(e)


@st.dialog("📜 대화 히스토리", width="large")
def show_history_dialog():
    """대화 히스토리 모달"""
    if not st.session_state.chat_history:
        st.info("아직 대화 히스토리가 없습니다.")
        return

    st.caption(f"총 {len(st.session_state.chat_history)}개의 메시지")
    for i, msg in enumerate(st.session_state.chat_history):
        role_icon = "👤" if msg["role"] == "user" else "🤖"
        with st.expander(f"{role_icon} {msg['role'].upper()} - {msg['content'][:50]}..."):
            st.markdown(msg["content"])
