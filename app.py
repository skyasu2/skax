import streamlit as st
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config import Config
from utils.llm import get_llm
from graph.workflow import run_plancraft
from mcp.file_utils import save_plan, list_saved_plans

# 페이지 설정
st.set_page_config(
    page_title="PlanCraft Agent",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일 - 컴팩트한 디자인
st.markdown("""
<style>
    /* 전체 여백 - 상단 여유 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 6rem;
    }

    /* 결과 카드 스타일 */
    .result-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        margin: 0.5rem 0;
    }

    /* 버튼 크기 조정 */
    .stButton > button {
        padding: 0.25rem 0.5rem;
        font-size: 0.9rem;
    }

    /* 하단 채팅 입력창 스타일 개선 */
    .stChatInput {
        border-top: 1px solid #e0e0e0;
        padding-top: 1rem;
        background: linear-gradient(to top, white 80%, transparent);
    }

    .stChatInput > div {
        max-width: 800px;
        margin: 0 auto;
    }

    /* 입력창 테두리 */
    .stChatInput textarea {
        border-radius: 24px !important;
        border: 2px solid #e0e0e0 !important;
        padding: 12px 20px !important;
    }

    .stChatInput textarea:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2) !important;
    }

    /* 전송 버튼 스타일 */
    .stChatInput button {
        border-radius: 50% !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
    }

    .stChatInput button:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """세션 상태 초기화"""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []  # 채팅 히스토리 [{role, content, type}]
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
        st.session_state.input_key = 0  # 입력창 초기화용 키
    if "prefill_prompt" not in st.session_state:
        st.session_state.prefill_prompt = None  # 예시 클릭 시 채울 프롬프트


def render_progress_steps(current_step: str = None):
    """진행 상태 표시"""
    steps = [
        ("retrieve", "📚 RAG"),
        ("fetch_web", "🌐 웹"),
        ("analyze", "🔍 분석"),
        ("structure", "📐 구조"),
        ("write", "✍️ 작성"),
        ("review", "📝 검토"),
        ("refine", "🔧 개선"),
        ("format", "✨ 정리")
    ]

    cols = st.columns(len(steps))
    step_order = [s[0] for s in steps]
    current_idx = step_order.index(current_step) if current_step in step_order else -1

    for i, (step_id, icon) in enumerate(steps):
        with cols[i]:
            if i < current_idx:
                st.markdown(f"<div style='text-align:center; color:#28a745;'>{icon}<br><small>✅</small></div>", unsafe_allow_html=True)
            elif i == current_idx:
                st.markdown(f"<div style='text-align:center; color:#ffc107;'>{icon}<br><small>⏳</small></div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center; color:#aaa;'>{icon}<br><small>-</small></div>", unsafe_allow_html=True)


def render_chat_message(role: str, content: str, msg_type: str = "text"):
    """채팅 메시지 렌더링"""
    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    else:  # assistant
        with st.chat_message("assistant"):
            st.markdown(content)


@st.dialog("📄 생성된 기획서", width="large")
def show_plan_dialog():
    """기획서 상세 보기 모달"""
    if not st.session_state.generated_plan:
        st.warning("생성된 기획서가 없습니다.")
        return

    # 결과 요약 - Refiner가 개선을 완료했으므로 항상 완성 상태
    if st.session_state.current_state:
        state = st.session_state.current_state
        refined = state.get("refined", False)

        col1, col2, col3 = st.columns(3)
        with col1:
            # 개선 완료 여부 표시
            status = "✅ 개선 완료" if refined else "✅ 완성"
            st.metric("상태", status)
        with col2:
            # 섹션 수 표시
            draft = state.get("draft", {})
            section_count = len(draft.get("sections", []))
            st.metric("섹션", f"{section_count}개")
        with col3:
            # 분석 기반 정보
            analysis = state.get("analysis", {})
            feature_count = len(analysis.get("key_features", []))
            st.metric("핵심 기능", f"{feature_count}개")

    # 탭
    tab1, tab2 = st.tabs(["📖 미리보기", "📝 마크다운"])
    with tab1:
        st.markdown(st.session_state.generated_plan)
    with tab2:
        st.code(st.session_state.generated_plan, language="markdown")

    # 버튼
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 다운로드",
            data=st.session_state.generated_plan,
            file_name="기획서.md",
            mime="text/markdown",
            use_container_width=True
        )
    with col2:
        if st.button("💾 저장", use_container_width=True):
            saved_path = save_plan(st.session_state.generated_plan)
            st.success(f"저장됨: {os.path.basename(saved_path)}")


@st.dialog("🔍 분석 결과", width="large")
def show_analysis_dialog():
    """분석 결과 상세 보기 모달"""
    if not st.session_state.current_state:
        st.warning("분석 결과가 없습니다.")
        return

    state = st.session_state.current_state

    if state.get("analysis"):
        st.subheader("🔍 입력 분석")
        st.json(state["analysis"])

    if state.get("structure"):
        st.subheader("📐 구조 설계")
        st.json(state["structure"])

    if state.get("review"):
        st.subheader("📝 검토 결과")
        st.json(state["review"])


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


def render_main():
    """메인 영역 렌더링"""
    # =========================================================================
    # 헤더 - 타이틀 + 버튼들을 한 줄에
    # =========================================================================
    col_title, col_spacer, col_new, col_history, col_file, col_settings = st.columns([3, 2, 1, 1, 1, 1])

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")

    with col_new:
        if st.button("🆕 새 대화", use_container_width=True, help="새로운 대화 시작"):
            st.session_state.chat_history = []
            st.session_state.current_state = None
            st.session_state.generated_plan = None
            st.session_state.input_key += 1
            st.rerun()

    with col_history:
        if st.button("📜 히스토리", use_container_width=True, help="대화 기록 보기"):
            show_history_dialog()

    with col_file:
        with st.popover("📁 파일"):
            st.markdown("**참고 파일 업로드**")
            uploaded_file = st.file_uploader(
                "파일",
                type=["txt", "md", "docx"],
                label_visibility="collapsed"
            )
            if uploaded_file:
                try:
                    st.session_state.uploaded_content = uploaded_file.read().decode("utf-8")
                    st.success(f"✅ {uploaded_file.name}")
                except:
                    st.error("실패")

    with col_settings:
        with st.popover("⚙️ 설정"):
            try:
                Config.validate()
                st.success("✅ Azure OpenAI 연결됨")
            except EnvironmentError as e:
                st.error("❌ 미연결")
            st.caption("Analyzer → Structurer → Writer → Reviewer")

    st.divider()

    # =========================================================================
    # 시작 화면 (채팅 히스토리가 없을 때)
    # =========================================================================
    if not st.session_state.chat_history:
        st.markdown("#### 💡 아이디어를 기획서로 만들어 드립니다")
        st.caption("아래 예시를 클릭하거나 직접 입력하세요")

        # 예시 템플릿
        examples = [
            ("🍽️ 점심 메뉴 추천 앱", "직장인을 위한 점심 메뉴 추천 서비스를 만들고 싶어요"),
            ("📚 독서 모임 플랫폼", "독서 모임을 쉽게 만들고 관리할 수 있는 서비스"),
            ("🏃 운동 챌린지 앱", "친구들과 함께 운동 목표를 달성하는 챌린지 앱"),
        ]

        cols = st.columns(len(examples))
        for i, (title, prompt) in enumerate(examples):
            with cols[i]:
                if st.button(title, key=f"example_{i}", use_container_width=True, help=prompt):
                    # 프롬프트만 채워주고 사용자가 엔터 치도록
                    st.session_state.prefill_prompt = prompt
                    st.rerun()

        st.divider()

    # =========================================================================
    # 채팅 히스토리 표시
    # =========================================================================
    for msg in st.session_state.chat_history:
        render_chat_message(msg["role"], msg["content"], msg.get("type", "text"))

    # =========================================================================
    # 옵션 선택 UI (need_more_info 상태일 때) - 컴팩트 버전
    # =========================================================================
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        options = st.session_state.current_state.get("options", [])

        if options:
            # 옵션 버튼들을 한 줄에 표시
            cols = st.columns(len(options))
            for i, opt in enumerate(options):
                title = opt.get("title", "")
                description = opt.get("description", "")
                with cols[i]:
                    if st.button(f"{title}", key=f"opt_{i}", use_container_width=True, help=description):
                        # 사용자 선택을 채팅에 추가
                        st.session_state.chat_history.append({
                            "role": "user",
                            "content": f"'{title}' 선택",
                            "type": "text"
                        })

                        # 선택한 옵션으로 다시 실행
                        original_input = st.session_state.current_state.get("user_input", "")
                        new_input = f"{original_input}\n\n[선택: {title} - {description}]"
                        st.session_state.current_state = None
                        st.session_state.pending_input = new_input
                        st.rerun()

            # 직접 입력 안내 - OR 구분선
            st.markdown("""
            <div style="display: flex; align-items: center; margin: 1.5rem 0 1rem 0;">
                <div style="flex: 1; height: 1px; background: #ddd;"></div>
                <span style="padding: 0 1rem; color: #888; font-size: 0.85rem;">또는 직접 입력</span>
                <div style="flex: 1; height: 1px; background: #ddd;"></div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("⌨️ 위 옵션 외에 다른 의견이 있다면 아래 입력창에 자유롭게 작성하세요")

    # =========================================================================
    # 기획서 결과 표시 (generated_plan 있을 때) - 간소화된 버전
    # =========================================================================
    if st.session_state.generated_plan:
        # 간단한 요약 카드
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            # 완성 상태만 표시 (내부 점수는 숨김)
            st.markdown("📄 **기획서 완성** ✅")

        with col2:
            if st.button("📖 기획서", key="view_plan", use_container_width=True, help="생성된 기획서 전체 보기"):
                show_plan_dialog()

        with col3:
            if st.button("🔍 분석", key="view_analysis", use_container_width=True, help="AI 분석 결과 상세 보기"):
                show_analysis_dialog()

        with col4:
            st.download_button(
                "📥 저장",
                data=st.session_state.generated_plan,
                file_name="기획서.md",
                mime="text/markdown",
                use_container_width=True,
                help="마크다운 파일로 다운로드"
            )

    # =========================================================================
    # pending_input 처리 (옵션 선택 후 자동 실행)
    # =========================================================================
    if st.session_state.pending_input:
        pending = st.session_state.pending_input
        st.session_state.pending_input = None

        with st.spinner("🔄 기획서를 생성하고 있습니다..."):
            try:
                file_content = st.session_state.get("uploaded_content", None)
                result = run_plancraft(pending, file_content)
                st.session_state.current_state = result

                if result.get("need_more_info"):
                    # 옵션 질문을 채팅에 추가
                    option_question = result.get("option_question", "어떤 방향으로 진행할까요?")
                    options = result.get("options", [])
                    option_text = f"🤔 **{option_question}**\n\n"
                    for opt in options:
                        option_text += f"- **{opt.get('title', '')}**: {opt.get('description', '')}\n"

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": option_text,
                        "type": "options"
                    })
                else:
                    # 완료 메시지를 채팅에 추가 (chat_summary 우선 사용)
                    st.session_state.generated_plan = result.get("final_output", "")
                    chat_summary = result.get("chat_summary", "")
                    if chat_summary:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": chat_summary,
                            "type": "summary"
                        })
                    else:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": "✅ 기획서가 완성되었습니다! 아래에서 확인하세요.",
                            "type": "plan"
                        })
            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"❌ 오류가 발생했습니다: {str(e)}",
                    "type": "error"
                })

        st.rerun()

    # =========================================================================
    # 채팅 입력 (하단 고정)
    # =========================================================================
    # prefill_prompt가 있으면 미리보기 표시
    if st.session_state.prefill_prompt:
        st.info(f"📝 **선택된 예시:** {st.session_state.prefill_prompt}")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ 이대로 시작", use_container_width=True):
                user_input = st.session_state.prefill_prompt
                st.session_state.prefill_prompt = None
                # 바로 실행
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_input,
                    "type": "text"
                })
                st.session_state.pending_input = user_input
                st.rerun()
        with col2:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.prefill_prompt = None
                st.rerun()

    # 채팅 입력창
    st.markdown("")  # 여백
    placeholder = "💬 만들고 싶은 서비스나 아이디어를 자유롭게 입력하세요..."
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        placeholder = "💬 위 옵션을 선택하거나, 다른 의견을 직접 입력하세요..."

    user_input = st.chat_input(
        placeholder,
        key=f"chat_input_{st.session_state.input_key}"
    )

    if user_input:
        # 사용자 메시지를 채팅 히스토리에 추가
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "type": "text"
        })

        # 입력창 초기화를 위해 키 변경
        st.session_state.input_key += 1

        # AI 응답 생성
        with st.spinner("🔄 AI Agent가 분석 중입니다..."):
            try:
                file_content = st.session_state.get("uploaded_content", None)
                result = run_plancraft(user_input, file_content)
                st.session_state.current_state = result

                if result.get("need_more_info"):
                    # 옵션 질문을 채팅에 추가
                    option_question = result.get("option_question", "어떤 방향으로 진행할까요?")
                    options = result.get("options", [])
                    option_text = f"🤔 **{option_question}**\n\n"
                    for opt in options:
                        option_text += f"- **{opt.get('title', '')}**: {opt.get('description', '')}\n"

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": option_text,
                        "type": "options"
                    })
                else:
                    # 완료 메시지 (chat_summary 우선 사용)
                    st.session_state.generated_plan = result.get("final_output", "")
                    chat_summary = result.get("chat_summary", "")
                    if chat_summary:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": chat_summary,
                            "type": "summary"
                        })
                    else:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": "✅ 기획서가 완성되었습니다! 아래에서 확인하세요.",
                            "type": "plan"
                        })
            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"❌ 오류가 발생했습니다: {str(e)}",
                    "type": "error"
                })

        st.rerun()


def main():
    """메인 함수"""
    init_session_state()
    render_main()


if __name__ == "__main__":
    main()
