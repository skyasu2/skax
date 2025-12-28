import streamlit as st
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config import Config
from utils.llm import get_llm
from graph.workflow import run_plancraft
from tools.file_utils import save_plan, list_saved_plans

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
        padding-bottom: 8rem; /* 하단 입력창 가림 방지 */
    }

    /* 결과 카드 스타일 */
    .result-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); /* 부드러운 그림자 추가 */
    }

    /* 버튼 크기 및 스타일 */
    .stButton > button {
        padding: 0.3rem 0.8rem;
        font-size: 0.9rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        border-color: #667eea;
        color: #667eea;
        background-color: #f0f4ff;
    }

    /* 하단 채팅 입력창 컨테이너 고정 및 스타일 */
    .stChatInput {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 1rem 1rem 2rem 1rem;
        background: linear-gradient(to top, #ffffff 90%, rgba(255,255,255,0)); /* 자연스런 페이드아웃 */
        z-index: 1000;
        border-top: none; /* 상단 선 제거 */
    }

    .stChatInput > div {
        max-width: 800px;
        margin: 0 auto;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1); /* 입력창 전체 그림자 */
        border-radius: 28px;
    }

    /* 입력창 내부 텍스트 영역 */
    .stChatInput textarea {
        border-radius: 28px !important;
        border: 1px solid #e0e0e0 !important; /* 더 얇은 테두리 */
        padding: 14px 24px !important;
        font-size: 1rem !important;
        background-color: #ffffff !important;
    }

    /* 포커스 시 스타일 */
    .stChatInput textarea:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2) !important;
    }
    
    /* Streamlit 기본 포커스 외곽선 제거 */
    .stChatInput div[data-baseweb="textarea"] {
        background-color: transparent !important;
        border: none !important;
    }
    
    .stChatInput div[data-baseweb="base-input"] {
         background-color: transparent !important;
    }

    /* 전송 버튼 스타일 */
    .stChatInput button[kind="primary"] {
        border-radius: 50% !important;
        width: 40px !important;
        height: 40px !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
        color: white !important;
        right: 10px !important; /* 우측 여백 확보 */
        top: 50% !important;
        transform: translateY(-50%) !important; /* 수직 중앙 정렬 */
    }

    .stChatInput button[kind="primary"]:hover {
        opacity: 0.9;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
    
    /* 전송 버튼 아이콘 크기 */
    .stChatInput button[kind="primary"] svg {
        width: 18px !important;
        height: 18px !important;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """세션 상태 초기화"""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []  # 채팅 히스토리 [{role, content, type}]
    if "plan_history" not in st.session_state:
        st.session_state.plan_history = [] # [{timestamp, content, version}]
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


# ... (중략) ...


@st.dialog("📄 생성된 기획서", width="large")
def show_plan_dialog():
    """기획서 상세 보기 모달 (버전 관리 포함)"""
    if not st.session_state.generated_plan:
        st.warning("생성된 기획서가 없습니다.")
        return

    # [추가] 버전 선택 UI
    history = st.session_state.get("plan_history", [])
    selected_plan = st.session_state.generated_plan
    is_latest = True
    
    if len(history) > 1:
        col_ver, col_empty = st.columns([1, 2])
        with col_ver:
            # 최신순 정렬 (역순)
            options = [f"v{h['version']} ({h['timestamp']})" for h in reversed(history)]
            selected_option = st.selectbox("🕒 버전 선택", options, index=0)
            
            # 선택된 버전 찾기
            version_str = selected_option.split("v")[1].split(" ")[0]
            version_idx = int(version_str)
            
            # 현재 최신 버전과 비교
            latest_version = history[-1]['version']
            is_latest = (version_idx == latest_version)
            
            for h in history:
                if h['version'] == version_idx:
                    selected_plan = h['content']
                    break
    
    if not is_latest:
        st.warning(f"⚠️ **v{version_idx} (과거 버전)**을 보고 있습니다. 현재 편집하거나 다운로드할 수 없습니다.")
    else:
        # 결과 요약 - Refiner가 개선을 완료했으므로 항상 완성 상태
        if st.session_state.current_state:
            state = st.session_state.current_state
            refined = state.get("refined", False)
            
            # [개선] 섹션 수 계산: 실제 마크다운 내용에서 헤더 카운트
            final_doc = selected_plan
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

            # [개선] 핵심 기능 수 계산
            analysis = state.get("analysis")
            key_features = []
            
            if analysis:
                if hasattr(analysis, "key_features"):
                     key_features = analysis.key_features
                elif isinstance(analysis, dict):
                     key_features = analysis.get("key_features", [])
            
            feature_count = len(key_features)
            
            if feature_count == 0 and final_doc:
                bullet_count = final_doc.count("\n- ")
                if bullet_count > 0:
                    feature_count = max(3, int(bullet_count * 0.3)) 

            col1, col2, col3 = st.columns(3)
            with col1:
                status = "✅ 개선 완료" if refined else "✅ 완성"
                st.metric("상태", status)
            with col2:
                st.metric("섹션", f"{section_count}개")
            with col3:
                st.metric("핵심 기능", f"{feature_count}개")

    # 탭
    tab1, tab2 = st.tabs(["📖 미리보기", "📝 마크다운"])
    with tab1:
        st.markdown(selected_plan)
    with tab2:
        st.code(selected_plan, language="markdown")

    # 버튼 (최신 버전일 때만 다운로드/저장 가능하게 함)
    if is_latest:
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 다운로드",
                data=selected_plan,
                file_name="기획서.md",
                mime="text/markdown",
                use_container_width=True
            )
        with col2:
            if st.button("💾 저장", use_container_width=True):
                saved_path = save_plan(selected_plan)
                st.success(f"저장됨: {os.path.basename(saved_path)}")


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

        # [수정] 불필요한 재실행 제거 (무한 루프 방지)
        # st.rerun()  <-- 제거됨

    # =========================================================================
    # [추가] 기획서 고도화 (Human Feedback Loop) - 최대 3회
    # =========================================================================
    if st.session_state.generated_plan and st.session_state.current_state:
        # 안전한 접근을 위해 get 사용
        current_refine_count = st.session_state.current_state.get("refine_count", 0)
        
        st.divider()
        st.divider()
        
        # [수정] UI 개선: Expander로 깔끔하게 정리
        next_step = current_refine_count + 1
        label = f"🔧 기획서 추가 개선 ({next_step}/3단계) - 클릭하여 펼치기"
        
        with st.expander(label, expanded=False):
            if current_refine_count < 3:
                st.info(f"💡 AI에게 피드백을 전달하여 기획서를 고도화할 수 있습니다. (남은 기회: **{3 - current_refine_count}회**)")
                
                with st.form("refine_form"):
                    st.markdown("**1. 추가 요청사항 입력**")
                    feedback = st.text_area(
                        "요청사항",
                        placeholder="예: '수익 모델을 구독형으로 바꿔줘', '경쟁사 분석 데이터를 더 추가해줘', '초기 마케팅 전략을 구체화해줘'",
                        height=100,
                        label_visibility="collapsed"
                    )
                    
                    st.markdown("**2. 참고 자료 첨부 (선택)**")
                    refine_file = st.file_uploader(
                        "파일 업로드",
                        type=["txt", "md", "pdf", "docx"],
                        label_visibility="collapsed",
                        help="기획서에 반영할 추가 자료가 있다면 업로드하세요."
                    )
                    
                    st.markdown("")
                    col_submit, col_info = st.columns([1, 4])
                    with col_submit:
                        is_submitted = st.form_submit_button("🚀 개선 수행", use_container_width=True)
                    with col_info:
                        st.caption(f"현재 **{next_step}단계** 개선을 진행합니다. (최대 3단계)")
                    
                    if is_submitted and feedback:
                        # 입력 데이터 구성
                        original_input = st.session_state.current_state.get("user_input", "")
                        # 이전 히스토리를 포함하여 문맥 유지 (형식: [기존] ... \n\n [추가 요청 1] ...)
                        new_input = f"{original_input}\n\n--- [추가 요청 {current_refine_count + 1}] ---\n{feedback}"
                        
                        # 파일 내용 읽기
                        new_file_content = st.session_state.get("uploaded_content", "")
                        if refine_file:
                            try:
                                # 기존 파일 내용에 추가
                                additional_content = refine_file.read().decode("utf-8")
                                new_file_content = (new_file_content + "\n\n" + additional_content) if new_file_content else additional_content
                                st.session_state.uploaded_content = new_file_content
                            except Exception as e:
                                st.error(f"파일 읽기 실패: {str(e)}")
                                
                        # 상태 업데이트 및 실행 예약
                        st.session_state.pending_input = new_input
                        
                        # 채팅창에 사용자 발화 추가
                        st.session_state.chat_history.append({
                            "role": "user",
                            "content": f"🛠 **추가 개선 요청 ({current_refine_count + 1}/3):**\n{feedback}",
                            "type": "text"
                        })
                        
                        # 임시로 현재 State의 카운트를 증가시켜 둠
                        st.session_state.next_refine_count = current_refine_count + 1
                        
                        st.rerun()

            else:
                st.info("✅ 최대 개선 횟수(3회)를 모두 사용했습니다. 새로운 기획을 원하시면 '새 대화'를 시작하세요.")

    # =========================================================================
    # pending_input 처리 (옵션 선택 후 자동 실행)
    # =========================================================================
    if st.session_state.pending_input:
        pending = st.session_state.pending_input
        st.session_state.pending_input = None
        
        # [중요] UI에서 설정한 next_refine_count가 있다면 가져와서 기억
        next_count = st.session_state.get("next_refine_count", 0)

        with st.spinner("🔄 기획서를 생성하고 있습니다..."):
            try:
                file_content = st.session_state.get("uploaded_content", None)
                current_plan = st.session_state.generated_plan
                
                # [수정] refine_count를 명시적으로 전달하여 Structurer 확장이 동작하도록 함
                result = run_plancraft(pending, file_content, refine_count=next_count, previous_plan=current_plan)
                
                # [중요] 개선 횟수 업데이트
                if next_count > 0:
                     result["refine_count"] = next_count
                     st.session_state.next_refine_count = 0  # 초기화
                     
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
                    # [추가] 일반 질문 답변 처리 (안전한 접근)
                    analysis_res = result.get("analysis")
                    is_general = False
                    general_ans = "죄송합니다, 답변을 생성할 수 없습니다."

                    if analysis_res:
                        # Pydantic 모델인 경우
                        if hasattr(analysis_res, "is_general_query"):
                             is_general = analysis_res.is_general_query
                             general_ans = getattr(analysis_res, "general_answer", general_ans)
                        # Dict인 경우
                        elif isinstance(analysis_res, dict):
                             is_general = analysis_res.get("is_general_query", False)
                             general_ans = analysis_res.get("general_answer", general_ans)
                    
                    if is_general:
                         st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": general_ans,
                            "type": "text"
                        })
                    else:
                        # 완료 메시지를 채팅에 추가 (chat_summary 우선 사용)
                        generated_plan = result.get("final_output", "")
                        st.session_state.generated_plan = generated_plan
                        
                        # [추가] 히스토리에 버전 저장
                        if generated_plan:
                            from datetime import datetime
                            now_str = datetime.now().strftime("%H:%M:%S")
                            new_version = len(st.session_state.plan_history) + 1
                            
                            # 중복 저장 방지
                            if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
                                st.session_state.plan_history.append({
                                    "version": new_version,
                                    "timestamp": now_str,
                                    "content": generated_plan
                                })

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
    # prefill_prompt가 있고 아직 대화가 시작되지 않았을 때만 표시
    if st.session_state.prefill_prompt and not st.session_state.chat_history:
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
        # 사용자 직접 입력 시 프롬프트 초기화
        st.session_state.prefill_prompt = None

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
                current_plan = st.session_state.generated_plan
                
                result = run_plancraft(user_input, file_content, previous_plan=current_plan)
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
                    # [추가] 일반 질문 답변 처리 (안전한 접근)
                    analysis_res = result.get("analysis")
                    is_general = False
                    general_ans = "죄송합니다, 답변을 생성할 수 없습니다."

                    if analysis_res:
                        # Pydantic 모델인 경우
                        if hasattr(analysis_res, "is_general_query"):
                             is_general = analysis_res.is_general_query
                             general_ans = getattr(analysis_res, "general_answer", general_ans)
                        # Dict인 경우
                        elif isinstance(analysis_res, dict):
                             is_general = analysis_res.get("is_general_query", False)
                             general_ans = analysis_res.get("general_answer", general_ans)
                    
                    if is_general:
                         st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": general_ans,
                            "type": "text"
                        })
                    else:
                        # 완료 메시지를 채팅에 추가 (chat_summary 우선 사용)
                        generated_plan = result.get("final_output", "")
                        st.session_state.generated_plan = generated_plan

                        # [추가] 히스토리에 버전 저장
                        if generated_plan:
                            from datetime import datetime
                            now_str = datetime.now().strftime("%H:%M:%S")
                            new_version = len(st.session_state.plan_history) + 1
                            
                            # 중복 저장 방지
                            if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
                                st.session_state.plan_history.append({
                                    "version": new_version,
                                    "timestamp": now_str,
                                    "content": generated_plan
                                })

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

def check_environment():
    """실행 환경 및 의존성 체크 (자동 초기화)"""
    # 1. 벡터 스토어 자동 초기화
    faiss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag", "faiss_index")
    
    if not os.path.exists(faiss_path) or not os.listdir(faiss_path):
        with st.spinner("📦 초기 설정 중... (벡터 데이터 생성)"):
            try:
                from rag.vectorstore import init_vectorstore
                init_vectorstore()
                st.toast("✅ 초기 설정 완료!", icon="🎉")
            except Exception as e:
                st.error(f"❌ 초기 설정 실패: {str(e)}")
                st.stop()


def main():
    """메인 함수"""
    # 환경 자동 체크
    check_environment()
    
    init_session_state()
    render_main()


if __name__ == "__main__":
    main()
