"""
Chat Module
"""
import streamlit as st

def render_chat_message(role: str, content: str, msg_type: str = "text"):
    """
    채팅 메시지 렌더링

    Args:
        role: "user" or "assistant"
        content: 메시지 내용
        msg_type: 메시지 유형
            - "text": 일반 텍스트 (기본값)
            - "plan": 기획서 완료 알림
            - "plan_content": 기획서 전문 (접힌 상태로 표시)
            - "guide": 후속 액션 안내
            - "summary": 채팅 요약
            - "options": 옵션 선택
            - "error": 에러 메시지
    """
    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    else:  # assistant
        with st.chat_message("assistant"):
            if msg_type == "plan_content":
                # 기획서 전문은 접힌 상태로 표시 (너무 길어서)
                with st.expander("📄 **생성된 기획서 전문** (클릭하여 펼치기)", expanded=False):
                    st.markdown(content)
            elif msg_type == "error":
                st.error(content)
            else:
                st.markdown(content)
