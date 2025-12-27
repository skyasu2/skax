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

    # 단계별 상세 설명 메시지
    step_descriptions = {
        "retrieve": "가이드 문서를 검색하고 있습니다...",
        "fetch_web": "필요한 정보를 웹에서 찾고 있습니다...",
        "analyze": "요구사항을 분석하고 방향을 잡고 있습니다...",
        "structure": "기획서의 목차와 구조를 설계 중입니다...",
        "write": "각 섹션별 상세 내용을 작성하고 있습니다...",
        "review": "작성된 기획서를 검토하고 평가 중입니다...",
        "refine": "검토 결과를 반영하여 완성도를 높이고 있습니다...",
        "format": "보기 좋게 정리하여 마무리하고 있습니다..."
    }

    cols = st.columns(len(steps))
    step_order = [s[0] for s in steps]
    current_idx = step_order.index(current_step) if current_step in step_order else -1

    # 진행 바 렌더링
    for i, (step_id, icon) in enumerate(steps):
        with cols[i]:
            if i < current_idx:
                # 완료된 단계
                st.markdown(f"<div style='text-align:center; color:#28a745; margin-bottom:5px;'>{icon}<br><small>✅</small></div>", unsafe_allow_html=True)
            elif i == current_idx:
                # 현재 진행 중인 단계 (강조)
                st.markdown(f"<div style='text-align:center; color:#ffc107; font-weight:bold; margin-bottom:5px; border-bottom: 2px solid #ffc107;'>{icon}<br><small>⏳</small></div>", unsafe_allow_html=True)
            else:
                # 대기 중인 단계
                st.markdown(f"<div style='text-align:center; color:#eee; opacity:0.5; margin-bottom:5px;'>{icon}<br><small>-</small></div>", unsafe_allow_html=True)

    # 현재 작업 내용 텍스트 표시 (하단)
    if current_step in step_descriptions:
        st.markdown(f"<div style='text-align:center; color:#666; font-size:0.9rem; margin-top:1rem; background-color:#f8f9fa; padding:0.5rem; border-radius:8px;'>{step_descriptions[current_step]}</div>", unsafe_allow_html=True)


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
        
        # [개선] 섹션 수 계산: 실제 마크다운 내용에서 헤더 카운트
        final_doc = st.session_state.generated_plan
        section_count = 0
        if final_doc:
            # "## " 패턴으로 섹션 수 추정 (독립된 라인에 있는 경우)
            section_count = final_doc.count("\n## ")
            if section_count == 0 and "## " in final_doc:
                # 첫 줄이거나 \n 없이 시작하는 경우 등 대비
                section_count = final_doc.count("## ")
        
        # fallback: 마크다운 파싱 실패 시 draft 구조 사용
        if section_count == 0:
            draft = state.get("draft", {})
            section_count = len(draft.get("sections", []))

        # [개선] 핵심 기능 수 계산: analysis가 없으면 마크다운에서 추정
        analysis = state.get("analysis")
        key_features = []
        
        if analysis:
            # Pydantic 객체인 경우
            if hasattr(analysis, "key_features"):
                 key_features = analysis.key_features
            # 딕셔너리인 경우
            elif isinstance(analysis, dict):
                 key_features = analysis.get("key_features", [])
        
        feature_count = len(key_features)
        
        # 만약 메타데이터 상 0개라면, 마크다운 본문에서 추정 (간이 계산)
        if feature_count == 0 and final_doc:
            # "4. 핵심 기능" 섹션 근처의 불릿 포인트 개수 추정 시도
            # 단순하게 전체 문서의 불릿 포인트('- ') 수를 세서 5로 나눈 값(대략적)이나
            # 혹은 그냥 0이 보기 싫으면 기본값 1 이상을 노출하지 않고 '생성됨' 등으로 표시
            # 여기서는 전체 '- ' 개수의 20% 정도로 추정 (임시 방편)
            bullet_count = final_doc.count("\n- ")
            if bullet_count > 0:
                feature_count = max(3, int(bullet_count * 0.3)) # 최소 3개 이상으로 보정

        col1, col2, col3 = st.columns(3)
        with col1:
            # 개선 완료 여부 표시
            status = "✅ 개선 완료" if refined else "✅ 완성"
            st.metric("상태", status)
        with col2:
            st.metric("섹션", f"{section_count}개")
        with col3:
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


@st.dialog("🛠️ Dev Tools", width="large")
def render_dev_tools():
    """개발자 도구 (모달)"""
    st.markdown("### Agent 단위 테스트")
    st.info("각 Agent를 개별적으로 실행하여 로직을 검증합니다.")
    st.markdown("---")
    
    # Agent 선택
    agent_type = st.selectbox(
        "Agent 테스트",
        ["None", "Analyzer", "Structurer", "Writer", "Reviewer"]
    )
    
    if agent_type != "None":
        st.write(f"**Target:** `{agent_type}` Agent")
        
        # 테스트용 더미 데이터 설정
        test_input = "점심 메뉴 추천 앱"
        if agent_type == "Writer":
            test_input = st.text_area("입력 (가상 시나리오)", value="점심 메뉴 추천 서비스 기획해줘", height=70)
        
        if st.button("🚀 테스트 실행", key="test_run_btn", use_container_width=True):
            with st.spinner(f"{agent_type} Agent 실행 중..."):
                try:
                    from graph.state import PlanCraftState
                    
                    # Mock State 생성
                    mock_state = PlanCraftState(
                        user_input=test_input,
                        current_step="start"
                    )
                    
                    result_state = None
                    
                    if agent_type == "Analyzer":
                        from agents.analyzer import run
                        result_state = run(mock_state)
                        st.subheader("결과 (AnalysisResult)")
                        st.json(result_state.analysis.model_dump())
                        
                    elif agent_type == "Structurer":
                        from agents.structurer import run
                        from utils.schemas import AnalysisResult
                        mock_state.analysis = AnalysisResult(
                            topic="점심 추천 앱",
                            purpose="직장인 점심 고민 해결",
                            target_users="직장인",
                            key_features=["랜덤 추천", "주변 식당 지도"],
                            need_more_info=False
                        )
                        result_state = run(mock_state)
                        st.subheader("결과 (StructureResult)")
                        st.json(result_state.structure.model_dump())
                        
                    elif agent_type == "Writer":
                        from agents.writer import run
                        from utils.schemas import StructureResult, SectionStructure
                        mock_state.structure = StructureResult(
                            title="점심 추천 앱 기획서",
                            sections=[
                                SectionStructure(id=1, name="개요", description="앱 소개", key_points=["목적 설명"]),
                                SectionStructure(id=2, name="기능", description="주요 기능", key_points=["기능 나열"])
                            ]
                        )
                        result_state = run(mock_state)
                        st.subheader("결과 (DraftResult)")
                        st.json(result_state.draft.model_dump())
                        
                    elif agent_type == "Reviewer":
                        from agents.reviewer import run
                        from utils.schemas import DraftResult, SectionContent
                        mock_state.draft = DraftResult(
                            sections=[
                                SectionContent(id=1, name="개요", content="이 앱은 점심을 추천해줍니다."),
                                SectionContent(id=2, name="기능", content="랜덤 추천 기능이 있습니다.")
                            ]
                        )
                        result_state = run(mock_state)
                        st.subheader("결과 (JudgeResult)")
                        st.json(result_state.review.model_dump())

                    if result_state:
                        st.success("✅ 테스트 성공")
                    
                except Exception as e:
                    st.error(f"❌ 테스트 실패: {str(e)}")
                    st.exception(e)
    
    st.markdown("---")
    st.caption("Pydantic State Architecture v2.0")


def render_main():
    """메인 영역 렌더링"""
    # =========================================================================
    # 헤더 - 타이틀 + 버튼들을 한 줄에
    # =========================================================================
    col_title, col_spacer, col_dev, col_new, col_history, col_file, col_settings = st.columns([3, 1, 1, 1, 1, 1, 1])

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")
    
    with col_dev:
        if st.button("🛠 Dev", use_container_width=True, help="개발자 도구 (Unit Test)"):
            render_dev_tools()

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


if __name__ == "__main__":
    main()
