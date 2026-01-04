"""
Plan Badges Module
"""
import streamlit as st

def render_plan_badges(state: dict):
    """
    기획서 생성에 사용된 모드와 품질 상태를 뱃지로 표시
    """
    
    # 1. 문서 유형 (IT vs 일반)
    analysis = state.get("analysis", {})
    if isinstance(analysis, dict):
        doc_type = analysis.get("doc_type", "web_app_plan")
    else:
        doc_type = "unknown"
        
    type_badge = "💻 IT 서비스 기획" if doc_type == "web_app_plan" else "📝 일반 사업 기획"

    # 2. 품질 모드 (session_state 활용)
    preset = st.session_state.get("generation_preset", "balanced")
    mode_map = {
        "balanced": ("⚖️ 균형 모드", "#e8f5e9", "#2e7d32"),       # 연한 초록 / 진한 초록
        "quality": ("💎 고품질 모드", "#f3e5f5", "#7b1fa2"),      # 연한 보라 / 진한 보라
        "speed": ("⚡ 속도 모드", "#fff3e0", "#ef6c00")           # 연한 주황 / 진한 주황
    }
    mode_text, mode_bg, mode_fg = mode_map.get(preset, mode_map["balanced"])

    # 3. 전략적 기능 활성화 여부
    features = []
    
    # 웹 검색 (Web Context 존재 여부)
    if state.get("web_context"):
        features.append(("🔍 Strategic Search", "#e3f2fd", "#1565c0")) # 파랑
        
    # RAG (Context 존재 여부)
    if state.get("rag_context"):
        features.append(("📚 RAG Knowledge", "#fff8e1", "#fbc02d"))   # 노랑

    # 4. 렌더링 (HTML) - 들여쓰기로 인한 코드블록 인식 방지를 위해 한 줄로 작성하거나 공백 제거
    badges_html = f"""
<div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; align-items: center;">
    <span style="background-color: #f1f3f5; color: #495057; padding: 4px 10px; border-radius: 16px; font-size: 0.8rem; font-weight: 600; border: 1px solid #dee2e6;">{type_badge}</span>
    <span style="background-color: {mode_bg}; color: {mode_fg}; padding: 4px 10px; border-radius: 16px; font-size: 0.8rem; font-weight: 600; border: 1px solid {mode_bg};">{mode_text}</span>"""
    
    for feat_text, bg, fg in features:
        badges_html += f"""
    <span style="background-color: {bg}; color: {fg}; padding: 4px 10px; border-radius: 16px; font-size: 0.8rem; font-weight: 600; border: 1px solid {bg};">{feat_text}</span>"""
        
    badges_html += "\n</div>"
    st.markdown(badges_html, unsafe_allow_html=True)
