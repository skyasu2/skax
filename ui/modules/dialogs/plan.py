"""
UI Dialog: Show Generated Plan
"""
import os
import streamlit as st
from ui.components import render_markdown_with_mermaid
from tools.file_utils import save_plan

@st.dialog("📄 생성된 기획서", width="large")
def show_plan_dialog():
    """기획서 상세 보기 모달 (버전 관리 포함)"""
    
    if not st.session_state.generated_plan:
        st.warning("생성된 기획서가 없습니다.")
        return

    # 버전 선택 UI
    history = st.session_state.get("plan_history", [])
    selected_plan = st.session_state.generated_plan
    is_latest = True
    
    if len(history) > 1:
        col_ver, col_empty = st.columns([1, 2])
        with col_ver:
            options = [f"v{h['version']} ({h['timestamp']})" for h in reversed(history)]
            selected_option = st.selectbox("🕒 버전 선택", options, index=0)
            
            version_str = selected_option.split("v")[1].split(" ")[0]
            version_idx = int(version_str)
            
            latest_version = history[-1]['version']
            is_latest = (version_idx == latest_version)
            
            for h in history:
                if h['version'] == version_idx:
                    selected_plan = h['content']
                    break
    
    if not is_latest:
        st.warning(f"⚠️ **v{version_idx} (과거 버전)**을 보고 있습니다. 현재 편집하거나 다운로드할 수 없습니다.")
    else:
        if st.session_state.current_state:
            state = st.session_state.current_state
            refined = state.get("refined", False)
            
            final_doc = selected_plan
            section_count = 0
            if final_doc:
                section_count = final_doc.count("\n## ")
                if section_count == 0 and "## " in final_doc:
                    section_count = final_doc.count("## ")
            
            if section_count == 0:
                draft = state.get("draft", {})
                section_count = len(draft.get("sections", []))

            # [FIX] 핵심 기능 개수를 최종 문서에서 직접 추출 (분석 결과와 동기화 문제 해결)
            feature_count = 0

            if final_doc:
                import re
                # 1. "핵심 기능" 섹션 찾기 (다음 메인 섹션 ##N. 전까지 캡처)
                # 정규식: "## 4. 핵심 기능" ~ "## 5. 비즈니스" 전까지 (###는 포함)
                feature_section_match = re.search(
                    r"(?:##\s*)?(?:\d+\.\s*)?핵심\s*기능.*?\n(.*?)(?=\n##\s*\d+\.|\n##\s*[가-힣]|\Z)",
                    final_doc,
                    re.DOTALL | re.IGNORECASE
                )

                if feature_section_match:
                    feature_content = feature_section_match.group(1)
                    # bullet points 카운팅 (-, *, 1. 등) - 기능명이 있는 줄만
                    # 예: "- 리뷰 작성 및 별점 부여: ..." 또는 "1. **기능명**"
                    bullets = re.findall(r"^\s*[-*]\s+\*?\*?[가-힣A-Za-z].+", feature_content, re.MULTILINE)
                    feature_count = len(bullets)

                # 2. 섹션을 못 찾으면 분석 결과 참조 (fallback)
                if feature_count == 0:
                    analysis = state.get("analysis")
                    if analysis:
                        from graph.state import safe_get
                        key_features = safe_get(analysis, "key_features", [])
                        feature_count = len(key_features) 

            col1, col2, col3 = st.columns(3)
            with col1:
                status = "✅ 개선 완료" if refined else "✅ 완성"
                st.metric("상태", status)
            with col2:
                st.metric("섹션 (목차 개수)", f"{section_count}개", 
                    help="기획서의 큰 목차(Chapter) 개수입니다.")
            with col3:
                st.metric("핵심 기능 (주요 아이디어)", f"{feature_count}개", 
                    help="AI가 분석한 이 서비스의 주요 기능입니다.")

    # 탭
    tab1, tab2 = st.tabs(["📖 미리보기", "📝 마크다운"])
    with tab1:
        # 뱃지 표시를 위해 현재 상태 전달 (최신 버전인 경우만)
        state_for_badge = st.session_state.current_state if is_latest else None
        render_markdown_with_mermaid(selected_plan, state=state_for_badge)
    with tab2:
        st.code(selected_plan, language="markdown")

    # 버튼
    if is_latest:
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.download_button("📥 다운로드", data=selected_plan, file_name="기획서.md",
                mime="text/markdown", use_container_width=True)
        with col2:
            if st.button("💾 서버에 저장", use_container_width=True):
                saved_path = save_plan(selected_plan)
                st.success(f"서버에 저장됨: {os.path.basename(saved_path)}")
        with col3:
            if st.button("✖️ 닫기", use_container_width=True):
                st.rerun()
