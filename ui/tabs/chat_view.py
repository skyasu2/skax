"""
Chat View Tab
"""
import streamlit as st
from datetime import datetime
from ui.components import (
    render_chat_message, render_error_state, render_human_interaction, 
    render_visual_timeline
)
from ui.dialogs import show_plan_dialog, show_analysis_dialog
from ui.refinement import render_refinement_ui

def render_chat_and_state():
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
