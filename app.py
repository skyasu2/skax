import streamlit as st
import os
import sys
import random
import uuid
from datetime import datetime

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
    if "thread_id" not in st.session_state:
        # [NEW] Time-Travel을 위한 고유 스레드 ID 생성
        st.session_state.thread_id = str(uuid.uuid4())
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
                st.metric(
                    "섹션 (목차 개수)", 
                    f"{section_count}개", 
                    help="기획서의 큰 목차(Chapter) 개수입니다. 내용이 얼마나 체계적으로 구성되었는지 보여줍니다."
                )
            with col3:
                st.metric(
                    "핵심 기능 (주요 아이디어)", 
                    f"{feature_count}개", 
                    help="AI가 분석한 이 서비스의 주요 기능 및 핵심 아이디어(Key Features)의 개수입니다."
                )

    # 탭
    tab1, tab2 = st.tabs(["📖 미리보기", "📝 마크다운"])
    with tab1:
        st.markdown(selected_plan)
    with tab2:
        st.code(selected_plan, language="markdown")

    # 버튼 (최신 버전일 때만 다운로드/저장 가능하게 함)
    if is_latest:
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 1])
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
        with col3:
            if st.button("✖️ 닫기", use_container_width=True):
                st.rerun()


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


def render_timeline(step_history: list):
    """LangGraph 실행 이력 타임라인 렌더링"""
    if not step_history:
        return

    st.markdown("##### ⏱️ 실행 타임라인")
    with st.expander("상세 실행 이력 보기", expanded=False):
        for i, item in enumerate(step_history):
            # 상태 아이콘
            status = item.get("status", "UNKNOWN")
            icon = "🟢" if status == "SUCCESS" else "🔴" if status == "FAILED" else "⚪"
            
            # 시간 포맷 (HH:MM:SS)
            ts = item.get("timestamp", "")
            time_str = ts.split("T")[1][:8] if "T" in ts else ts
            
            # 단계 이름 (첫 글자 대문자)
            step_name = item.get("step", "").upper()
            
            # 요약 및 에러
            summary = item.get("summary", "")
            error = item.get("error")
            
            # Markdown 렌더링
            col1, col2 = st.columns([0.1, 0.9])
            with col1:
                st.markdown(f"<div style='font-size:1.2em; text-align:center;'>{icon}</div>", unsafe_allow_html=True)
            with col2:
                st.markdown(f"**{step_name}** <small style='color:gray'>({time_str})</small>", unsafe_allow_html=True)
                if summary:
                    st.caption(f"└ {summary}")
                if error:
                    st.error(f"Error: {error}")
            
            if i < len(step_history) - 1:
                st.divider()


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
    tab_test, tab_graph, tab_history, tab_schema = st.tabs(["🧪 Agent Unit Test", "📊 Workflow Graph", "🕰️ State History", "📐 Schema Viewer"])
    
    with tab_test:
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
    
    with tab_graph:
        st.markdown("---")
        st.subheader("📊 Workflow Visualization")
        try:
            from graph.workflow import app as workflow_app
            mermaid_code = workflow_app.get_graph().draw_mermaid()
            st.markdown(f"```mermaid\n{mermaid_code}\n```")
        except Exception as e:
            st.warning(f"Graph Visualization unavailable: {e}")

    with tab_history:
        st.subheader("🕰️ Time-Travel Debugger")
        st.info(f"Current Thread ID: `{st.session_state.get('thread_id', 'unknown')}`")
        
        col_refresh, col_clear = st.columns([1, 1])
        with col_refresh:
            refresh_clicked = st.button("🔄 Refresh History", key="btn_refresh_hist", use_container_width=True)
        with col_clear:
            if st.button("🗑️ Clear History", key="btn_clear_hist", use_container_width=True):
                st.session_state.pop("history_cache", None)
                st.success("히스토리 캐시가 초기화되었습니다.")
        
        if refresh_clicked:
            try:
                from graph.workflow import app as workflow_app
                if "thread_id" in st.session_state:
                    config = {"configurable": {"thread_id": st.session_state.thread_id}}
                    history = list(workflow_app.get_state_history(config))
                    st.session_state.history_cache = history  # 캐시 저장
                else:
                    st.warning("Thread ID가 초기화되지 않았습니다.")
                    history = []
            except Exception as e:
                st.error(f"히스토리 조회 실패: {str(e)}")
                history = []
        else:
            history = st.session_state.get("history_cache", [])
        
        if not history:
            st.info("🔍 'Refresh History' 버튼을 클릭하여 실행 이력을 불러오세요.")
        else:
            st.success(f"총 {len(history)}개의 스냅샷이 있습니다.")
            
            for i, h in enumerate(history):
                ts = str(h.created_at)[:19] if h.created_at else "Unknown"
                next_step = h.next[0] if h.next else "END"
                
                with st.expander(f"#{i+1} | {next_step.upper()} | {ts}", expanded=(i==0)):
                    col_info, col_action = st.columns([3, 1])
                    
                    with col_info:
                        st.write(f"**Next Step:** `{next_step}`")
                        st.write(f"**Checkpoint ID:** `{h.config.get('configurable', {}).get('checkpoint_id', 'N/A')}`")
                    
                    with col_action:
                        # 롤백 버튼 (현재 스냅샷이 아닌 경우에만)
                        if i > 0:
                            if st.button(f"⏪ 롤백", key=f"rollback_{i}", use_container_width=True):
                                try:
                                    from graph.workflow import app as workflow_app
                                    # 해당 checkpoint로 상태 업데이트
                                    workflow_app.update_state(
                                        h.config,
                                        h.values,
                                        as_node=h.next[0] if h.next else None
                                    )
                                    # 세션 상태 동기화
                                    st.session_state.current_state = h.values
                                    if h.values.get("final_output"):
                                        st.session_state.generated_plan = h.values.get("final_output")
                                    st.success(f"✅ #{i+1} 시점으로 롤백되었습니다!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"롤백 실패: {str(e)}")
                        else:
                            st.caption("(현재)")
                    
                    # 상태 값 보기
                    with st.container():
                        st.json(h.values)
    
    # [NEW] Schema Viewer 탭
    with tab_schema:
        st.subheader("📐 Pydantic Schema Viewer")
        st.info("State 및 Output 스키마를 JSON Schema 형태로 확인할 수 있습니다. 동적 폼 생성의 기반 데이터입니다.")
        
        schema_type = st.selectbox(
            "스키마 선택",
            ["PlanCraftState", "AnalysisResult", "StructureResult", "DraftResult", "JudgeResult"],
            key="schema_select"
        )
        
        try:
            if schema_type == "PlanCraftState":
                from graph.state import PlanCraftState
                schema = PlanCraftState.model_json_schema()
            elif schema_type == "AnalysisResult":
                from utils.schemas import AnalysisResult
                schema = AnalysisResult.model_json_schema()
            elif schema_type == "StructureResult":
                from utils.schemas import StructureResult
                schema = StructureResult.model_json_schema()
            elif schema_type == "DraftResult":
                from utils.schemas import DraftResult
                schema = DraftResult.model_json_schema()
            elif schema_type == "JudgeResult":
                from utils.schemas import JudgeResult
                schema = JudgeResult.model_json_schema()
            else:
                schema = {}
            
            st.json(schema)
            
            # 필드 요약
            if "properties" in schema:
                st.markdown("#### 📋 필드 요약")
                for field_name, field_info in schema.get("properties", {}).items():
                    field_type = field_info.get("type", field_info.get("anyOf", "complex"))
                    description = field_info.get("description", "")
                    st.markdown(f"- **`{field_name}`** ({field_type}): {description}")
                    
        except Exception as e:
            st.error(f"스키마 로드 실패: {str(e)}")
    
    st.markdown("---")
    st.caption("Pydantic State Architecture v2.0 | Time-Travel Enabled")


def render_refinement_ui():
    """기획서 고도화 UI (개선 요청)"""
    if st.session_state.generated_plan and st.session_state.current_state:
        current_refine_count = st.session_state.current_state.get("refine_count", 0)
        
        st.divider()
        
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
                        # 이전 히스토리를 포함하여 문맥 유지
                        new_input = f"{original_input}\n\n--- [추가 요청 {current_refine_count + 1}] ---\n{feedback}"
                        
                        # 파일 내용 읽기
                        new_file_content = st.session_state.get("uploaded_content", "")
                        if refine_file:
                            try:
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
                        
                        st.session_state.next_refine_count = current_refine_count + 1
                        st.rerun()

            else:
                st.info("✅ 최대 개선 횟수(3회)를 모두 사용했습니다. 새로운 기획을 원하시면 '새 대화'를 시작하세요.")
        
        # [NEW] 새 대화 시작 버튼 (개선 UI 아래)
        st.markdown("")  # 간격
        if st.button("🔄 새 대화 시작", key="new_chat_after_plan", use_container_width=True):
            # 세션 초기화
            st.session_state.chat_history = []
            st.session_state.current_state = None
            st.session_state.generated_plan = None
            st.session_state.input_key = st.session_state.get("input_key", 0) + 1
            st.session_state.thread_id = __import__("uuid").uuid4().__str__()
            st.session_state.prefill_prompt = None
            st.session_state.pending_input = None
            st.session_state.next_refine_count = 0
            st.rerun()


def render_main():
    """메인 영역 렌더링"""
    # =========================================================================
    # 헤더 - 타이틀 + 버튼들을 한 줄에
    # =========================================================================
    # =========================================================================
    # 헤더 - 타이틀 + 통합 메뉴
    # =========================================================================
    col_title, col_menu = st.columns([6, 1]) # 6:1 비율

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")
    
    with col_menu:
        # 통합 메뉴 버튼 (햄버거 메뉴 스타일)
        with st.popover("메뉴"):
            st.caption("PlanCraft v2.1")
            
            if st.button("🆕 새 대화 시작", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.current_state = None
                st.session_state.generated_plan = None
                st.session_state.input_key += 1
                st.session_state.thread_id = str(uuid.uuid4()) # 새 대화 시작 시 thread_id 재생성
                st.rerun()
                
            if st.button("📜 대화 히스토리", use_container_width=True):
                show_history_dialog()
            
            st.divider()
            
            if st.button("🛠 개발자 도구 (Dev)", use_container_width=True):
                render_dev_tools()
                
            with st.expander("⚙️ 설정 / 상태"):
                try:
                    Config.validate()
                    st.success("Cloud: Azure OpenAI ✅")
                except EnvironmentError:
                    st.error("Cloud: Disconnected ❌")
                st.caption("Pipeline: Analyzer → Structurer → Writer")

    st.divider()

    # =========================================================================
    # 시작 화면 (채팅 히스토리가 없을 때)
    # =========================================================================
    if not st.session_state.chat_history:
        # [UI 개선] 심플한 Hero 섹션 (입력창 제거, 하단 유도)
        st.markdown(
            """
            <div style="text-align: center; margin-top: 4vh; margin-bottom: 3rem;">
                <h1>💡 무엇을 도와드릴까요?</h1>
                <p style="color: #666; font-size: 1.1rem; line-height: 1.6;">
                    <b>PlanCraft AI</b>가 아이디어를 구체적인 기획서로 만들어 드립니다.<br>
                    웹 서비스, 앱, 창업, 사업계획서 등 무엇이든 물어보세요.
                </p>
                <div style="margin-top: 1rem; color: #888; font-size: 0.9rem;">
                    👇 아래 <b>채팅창</b>에 입력하거나, 추천 <b>예시</b>를 선택하세요.
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # 예제 데이터 로드 (랜덤)
        if "random_examples" not in st.session_state or st.session_state.random_examples is None:
             import random
             from utils.prompt_examples import WEB_APP_POOL, NON_IT_POOL
             # Web 1개 + Non-IT 2개
             st.session_state.random_examples = random.sample(WEB_APP_POOL, 1) + random.sample(NON_IT_POOL, 2)

        # 예제 버튼 렌더링
        col_ex_head, col_ex_refresh = st.columns([6, 1], vertical_alignment="bottom")
        with col_ex_head:
            st.markdown("#### 🎲 추천 아이디어")
        with col_ex_refresh:
            if st.button("🔄 변경", key="refresh_hero_ex"):
                st.session_state.random_examples = None
                st.rerun()

        cols = st.columns(3)
        for i, (title, prompt) in enumerate(st.session_state.random_examples):
             with cols[i]:
                 if st.button(title, key=f"hero_ex_{i}", use_container_width=True, help=prompt):
                     st.session_state.prefill_prompt = prompt
                     st.rerun()
        
        st.divider()

    # =========================================================================
    # 채팅 히스토리 표시
    # =========================================================================
    for msg in st.session_state.chat_history:
        render_chat_message(msg["role"], msg["content"], msg.get("type", "text"))

    # =========================================================================
    # 옵션 선택 UI (need_more_info 상태일 때)
    # =========================================================================
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        options = st.session_state.current_state.get("options", [])

        if options:
            cols = st.columns(len(options))
            for i, opt in enumerate(options):
                title = opt.get("title", "")
                description = opt.get("description", "")
                with cols[i]:
                    if st.button(f"{title}", key=f"opt_{i}", use_container_width=True, help=description):
                        # 사용자 선택 추가
                        st.session_state.chat_history.append({
                            "role": "user",
                            "content": f"'{title}' 선택",
                            "type": "text"
                        })
                        
                        # 선택 입력 처리
                        original_input = st.session_state.current_state.get("user_input", "")
                        new_input = f"{original_input}\n\n[선택: {title} - {description}]"
                        st.session_state.current_state = None
                        st.session_state.pending_input = new_input
                        st.rerun()

            st.markdown("""
            <div style="display: flex; align-items: center; margin: 1.5rem 0 1rem 0;">
                <div style="flex: 1; height: 1px; background: #ddd;"></div>
                <span style="padding: 0 1rem; color: #888; font-size: 0.85rem;">또는 직접 입력</span>
                <div style="flex: 1; height: 1px; background: #ddd;"></div>
            </div>
            """, unsafe_allow_html=True)
            st.caption("⌨️ 위 옵션 외에 다른 의견이 있다면 아래 입력창에 자유롭게 작성하세요")

    # =========================================================================
    # 기획서 결과 표시 (generated_plan 있을 때)
    # =========================================================================
    if st.session_state.generated_plan:
        # [NEW] 실행 이력 타임라인 표시
        if st.session_state.current_state:
            hist = st.session_state.current_state.get("step_history", [])
            if hist:
                render_timeline(hist)
                st.markdown("---")

        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            st.markdown("📄 **기획서 완성** ✅")

        with col2:
            if st.button("📖 기획서", key="view_plan", use_container_width=True):
                show_plan_dialog()

        with col3:
            if st.button("🔍 분석", key="view_analysis", use_container_width=True):
                show_analysis_dialog()

        with col4:
            st.download_button(
                "📥 저장",
                data=st.session_state.generated_plan,
                file_name=f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )
            
        render_refinement_ui()

    # =========================================================================
    # 하단 입력 영역 (항상 표시: 파일 업로드 + 채팅창)
    # =========================================================================
    
    # 1. 파일 업로드 (채팅창 위에 배치)
    st.markdown("---")
    with st.expander("📎 참고 자료 추가 (파일 업로드)", expanded=False):
        uploaded_file = st.file_uploader(
            "기획서 생성에 참고할 파일 (PDF, DOCX, TXT 등)",
            type=["txt", "md", "docx", "pdf"],
            key="file_uploader_bottom"
        )
        if uploaded_file:
            try:
                content = uploaded_file.read().decode("utf-8", errors='ignore')
                st.session_state.uploaded_content = content
                st.success(f"✅ '{uploaded_file.name}' 업로드됨")
            except Exception as e:
                st.error(f"파일 읽기 실패: {str(e)}")

    # 2. Prefill 확인 UI (예제 선택 시 표시)
    if st.session_state.prefill_prompt and not st.session_state.pending_input:
        st.info(f"📝 **선택된 예시:** {st.session_state.prefill_prompt}")
        col_ok, col_no = st.columns([1, 1])
        with col_ok:
            if st.button("✅ 이대로 시작", use_container_width=True):
                user_msg = st.session_state.prefill_prompt
                st.session_state.prefill_prompt = None
                
                # 히스토리 추가 & 실행 대기
                st.session_state.chat_history.append({"role": "user", "content": user_msg, "type": "text"})
                st.session_state.pending_input = user_msg
                st.rerun()
        with col_no:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.prefill_prompt = None
                st.rerun()

    # 3. 채팅 입력창 (조건부 문구)
    placeholder = "💬 자유롭게 대화를 입력하세요..."
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        placeholder = "💬 위 옵션을 선택하거나, 다른 의견을 직접 입력하세요..."

    user_input = st.chat_input(placeholder, key=f"chat_input_{st.session_state.input_key}")

    if user_input:
        st.session_state.prefill_prompt = None
        st.session_state.chat_history.append({"role": "user", "content": user_input, "type": "text"})
        st.session_state.input_key += 1
        st.session_state.pending_input = user_input
        st.rerun()

    # =========================================================================
    # Pending Input 처리 (실제 실행 로직)
    # =========================================================================
    if st.session_state.pending_input:
        pending_text = st.session_state.pending_input
        st.session_state.pending_input = None
        current_refine_count = st.session_state.get("next_refine_count", 0)
        previous_plan = st.session_state.generated_plan

        from utils.streamlit_callback import StreamlitStatusCallback

        with st.status("🚀 기획서를 생성하고 있습니다...", expanded=True) as status:
            try:
                streamlit_callback = StreamlitStatusCallback(status)
                
                file_content = st.session_state.get("uploaded_content", None)
                
                final_result = run_plancraft(
                    user_input=pending_text, 
                    file_content=file_content,
                    refine_count=current_refine_count,
                    previous_plan=previous_plan,
                    callbacks=[streamlit_callback],
                    thread_id=st.session_state.thread_id # [NEW]
                )
                
                status.update(label="✅ 과정 완료!", state="complete", expanded=False)
                
                st.session_state.current_state = final_result

                # 개선 횟수 초기화
                if current_refine_count > 0:
                     final_result["refine_count"] = current_refine_count
                     st.session_state.next_refine_count = 0

                # (결과 처리 로직)
                analysis_res = final_result.get("analysis")
                generated_plan = final_result.get("final_output", "")
                need_more_info = final_result.get("need_more_info", False)

                if need_more_info:
                    q = final_result.get("option_question", "추가 정보가 필요합니다.")
                    opts = final_result.get("options", [])
                    msg_content = f"🤔 **{q}**\n\n"
                    for o in opts:
                        msg_content += f"- **{o.get('title')}**: {o.get('description')}\n"
                    
                    st.session_state.chat_history.append({"role": "assistant", "content": msg_content, "type": "options"})

                elif generated_plan:
                    st.session_state.generated_plan = generated_plan
                    st.session_state.chat_history.append({"role": "assistant", "content": "✅ 기획서가 완성되었습니다!", "type": "plan"})
                    
                    # 히스토리 저장
                    now_str = datetime.now().strftime("%H:%M:%S")
                    new_version = len(st.session_state.plan_history) + 1
                    
                    if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
                         st.session_state.plan_history.append({
                            "version": new_version,
                            "timestamp": now_str,
                            "content": generated_plan
                         })

                    chat_summary = final_result.get("chat_summary", "")
                    if chat_summary:
                        st.session_state.chat_history.append({"role": "assistant", "content": chat_summary, "type": "summary"})
                
                else:
                    ans = "죄송합니다, 적절한 응답을 생성하지 못했습니다."
                    is_general = False
                    if analysis_res:
                         if isinstance(analysis_res, dict):
                             is_general = analysis_res.get("is_general_query", False)
                             ans = analysis_res.get("general_answer", ans)
                         elif hasattr(analysis_res, "is_general_query"):
                             is_general = analysis_res.is_general_query
                             ans = getattr(analysis_res, "general_answer", ans)
                    
                    st.session_state.chat_history.append({"role": "assistant", "content": ans, "type": "text"})

            except Exception as e:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"❌ 오류 발생: {str(e)}",
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
