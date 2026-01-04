"""
Hero Tab: Brainstorming UI
"""
import streamlit as st
from utils.prompt_examples import CATEGORIES, get_examples_by_category

def render_brainstorming_hero():
    """시작 화면 브레인스토밍 UI"""
    st.markdown("<div class='animate-fade-in' style='margin-top: 0.5rem;'>", unsafe_allow_html=True)

    # 세션 상태 초기화
    if "idea_category" not in st.session_state:
        st.session_state.idea_category = "random"
    if "idea_llm_count" not in st.session_state:
        st.session_state.idea_llm_count = 0
    if "random_examples" not in st.session_state or st.session_state.random_examples is None:
        from utils.prompt_examples import get_examples_by_category
        st.session_state.random_examples = get_examples_by_category("random", 3)

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
    <div class="animate-slide-up hover-lift" style="
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
    
    # Close animation wrapper
    st.markdown("</div>", unsafe_allow_html=True)
