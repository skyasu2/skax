"""
PlanCraft Agent - Main Application

AI 기반 기획서 자동 생성 서비스입니다.
LangGraph 워크플로우와 Azure OpenAI를 활용합니다.
"""

import streamlit as st
import os
import sys
import random
import uuid
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config import Config
from graph.workflow import run_plancraft

# UI 컴포넌트 Import (분리된 모듈에서)
from ui import (
    render_timeline,
    render_chat_message,
    show_plan_dialog,
    show_analysis_dialog,
    show_history_dialog,
    render_dev_tools,
    render_refinement_ui,
    render_error_state,
    render_option_selector,
    render_visual_timeline,
    render_human_interaction  # [NEW]
)
# from ui.components import render_structure_dialog  # [REMOVED] Structure Approval Deprecated

# =============================================================================
# 페이지 설정
# =============================================================================
st.set_page_config(
    page_title="PlanCraft Agent",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================================================================
# CSS 스타일
# =============================================================================
from ui.styles import CUSTOM_CSS
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# 세션 상태 초기화
# =============================================================================
def init_session_state():
    """세션 상태 초기화"""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "plan_history" not in st.session_state:
        st.session_state.plan_history = []
    if "thread_id" not in st.session_state:
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
        st.session_state.input_key = 0
    if "prefill_prompt" not in st.session_state:
        st.session_state.prefill_prompt = None
    # [NEW] 알림 트리거 플래그
    if "trigger_notification" not in st.session_state:
        st.session_state.trigger_notification = False
    # [FIX] 생성 모드 프리셋 기본값 (balanced = 균형)
    if "generation_preset" not in st.session_state:
        st.session_state.generation_preset = "balanced"


# =============================================================================
# 리소스 초기화 (RAG, Config 등)
# =============================================================================
@st.cache_resource
def init_resources():
    """
    앱 실행 시 무거운 리소스를 초기화합니다.
    st.cache_resource를 사용하여 프로세스당 1회만 실행되도록 합니다.
    """
    try:
        # 1. Config 검증
        Config.validate()
        
        # 2. RAG 벡터스토어 로드 (없으면 생성)
        # 배포 환경에서 첫 실행 시 인덱스를 생성합니다.
        # 네트워크 문제(403) 발생 시에도 앱이 멈추지 않도록 예외 처리합니다.
        from rag.vectorstore import load_vectorstore
        print("[INIT] Loading RAG Vectorstore...")
        vs = load_vectorstore()
        if vs:
             print("[INIT] RAG Vectorstore Loaded Successfully")
        else:
             print("[WARN] RAG Vectorstore Load Failed (None)")
             
    except Exception as e:
        print(f"[WARN] Resource Initialization Warning: {e}")
        # 치명적이지 않은 오류는 로그만 남기고 진행




# =============================================================================
# 메인 렌더링
# =============================================================================
def render_main():
    """메인 영역 렌더링"""
    # =========================================================================
    # 헤더
    # =========================================================================
    
    # [CHECK] 예약된 알림이 있으면 실행
    if st.session_state.get("trigger_notification"):
        from ui.components import trigger_browser_notification
        trigger_browser_notification("PlanCraft 알림", "기획서 작성이 완료되었습니다! 📄")
        st.session_state.trigger_notification = False

    # 헤더: 타이틀 | 프리셋 선택 | 메뉴
    # [FIX] 프리셋 설명이 잘리지 않도록 컬럼 비율 조정 (1.5 -> 2.5)
    col_title, col_preset, col_menu = st.columns([4, 2.5, 0.5])

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")

    # [NEW] 프리셋 선택기 - 헤더에 직접 배치
    with col_preset:
        from utils.settings import GENERATION_PRESETS, DEFAULT_PRESET

        # 프리셋 드롭다운 옵션
        preset_keys = list(GENERATION_PRESETS.keys())

        # [FIX] Streamlit 위젯 key와 session_state 충돌 방지
        # - key 사용 시 index 파라미터 제거 (Streamlit 권장 패턴)
        # - 기본값은 init_session_state()에서 설정
        st.selectbox(
            "생성 모드",
            options=preset_keys,
            format_func=lambda k: f"{GENERATION_PRESETS[k].icon} {GENERATION_PRESETS[k].name} ({GENERATION_PRESETS[k].description})",
            key="generation_preset",
            label_visibility="collapsed",
            help="⚡빠른(GPT-4o-mini): 속도/가성비 | ⚖️균형(GPT-4o): 표준 | 💎고품질(GPT-4o+Deep): 심층분석"
        )

    with col_menu:
        with st.popover("☰"):
            st.caption("PlanCraft v2.1")

            if st.button("🆕 새 대화 시작", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.current_state = None
                st.session_state.generated_plan = None
                st.session_state.input_key += 1
                st.session_state.thread_id = str(uuid.uuid4())
                # 브레인스토밍 상태 초기화
                st.session_state.idea_category = "random"
                st.session_state.idea_llm_count = 0
                st.session_state.random_examples = None
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
    # 시작 화면 (채팅 히스토리가 없을 때만 표시)
    # =========================================================================
    if not st.session_state.chat_history:
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

        # 세션 상태 초기화
        if "idea_category" not in st.session_state:
            st.session_state.idea_category = "random"
        if "idea_llm_count" not in st.session_state:
            st.session_state.idea_llm_count = 0
        if "random_examples" not in st.session_state or st.session_state.random_examples is None:
            from utils.prompt_examples import get_examples_by_category
            st.session_state.random_examples = get_examples_by_category("random", 3)

        # 카테고리 드롭다운 & AI 생성 버튼 (한 줄로 통합)
        from utils.prompt_examples import CATEGORIES, get_examples_by_category

        # 카테고리 드롭다운 (format_func 패턴 - 베스트 프랙티스)
        cat_keys = list(CATEGORIES.keys())

        # 카테고리 변경 시 예시 갱신 (side effect가 필요한 경우만 on_change 사용)
        def on_category_change():
            new_category = st.session_state.idea_category
            st.session_state.random_examples = get_examples_by_category(new_category, 3)

        # 헤더 + 드롭다운 + 버튼을 한 줄로
        llm_remaining = max(0, 10 - st.session_state.idea_llm_count)
        col_title, col_dropdown, col_btn = st.columns([2.5, 1.5, 1])

        with col_title:
            st.markdown(f"#### 🎲 AI 브레인스토밍 <small style='color:gray;'>({llm_remaining}회)</small>", unsafe_allow_html=True)

        with col_dropdown:
            st.selectbox(
                "카테고리",
                options=cat_keys,
                # index 제거: session_state.idea_category가 자동으로 선택값 결정
                format_func=lambda k: f"{CATEGORIES[k]['icon']} {CATEGORIES[k]['label']}",
                key="idea_category",  # session_state key와 동일 → 자동 동기화
                label_visibility="collapsed",
                on_change=on_category_change  # 예시 갱신을 위한 side effect
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

        # 카테고리 설명
        current_cat = CATEGORIES.get(st.session_state.idea_category, {})
        st.caption(f"💡 {current_cat.get('description', '')}")

        # 아이디어 카드
        cols = st.columns(3)
        for i, (title, prompt) in enumerate(st.session_state.random_examples):
            with cols[i]:
                if st.button(title, key=f"hero_ex_{i}", use_container_width=True, help=prompt):
                    st.session_state.prefill_prompt = prompt

        # [NEW] 입력 팁 안내
        st.markdown("""
        <div style="
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

    # =========================================================================
    # 3. 화면 렌더링 (채팅 히스토리 & 현재 상태 UI) [위치 이동됨]
    # =========================================================================
    
    # 3-1. 채팅 히스토리
    for msg in st.session_state.chat_history:
        render_chat_message(msg["role"], msg["content"], msg.get("type", "text"))

    # 3-2. 현재 상태 기반 UI (인터럽트, 에러, 결과)
    if st.session_state.current_state:
        state = st.session_state.current_state
        
        # A. 에러
        if state.get("error") or state.get("error_message"):
            render_error_state(state)
            
        # B. 인터럽트 (Native Payload 우선)
        elif state.get("__interrupt__"):
            payload = state["__interrupt__"]
            
            # [CASE] 목차 승인 (Multi-HITL) - 모달 & Fast Track
            # [CASE] 일반 옵션 선택 (기존 로직)
            ui_state = state.copy() 
            ui_state.update({
                "input_schema_name": payload.get("input_schema_name"),
                "options": payload.get("options"),
                "option_question": payload.get("question"),
                "error": payload.get("error"),  # [NEW] 에러 메시지 전달 (UI 표시용)
                "need_more_info": True
            })
            render_human_interaction(ui_state)
            
        # C. 기존 방식 호환 (need_more_info 플래그)
        elif state.get("need_more_info"):
            render_human_interaction(state)
            
        # D. 최종 결과
        elif state.get("final_output") and not state.get("analysis", {}).get("is_general_query", False):
             st.success("기획서 작성이 완료되었습니다!")
             st.session_state.generated_plan = state["final_output"]
             
             # 히스토리 중복 방지
             if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != state["final_output"]:
                 now_str = datetime.now().strftime("%H:%M:%S")
                 st.session_state.plan_history.append({
                    "version": len(st.session_state.plan_history) + 1,
                    "timestamp": now_str,
                    "content": state["final_output"]
                 })

             st.divider()
             # 메인 액션 버튼 (모달 호출)
             col_act1, col_act2 = st.columns(2)
             with col_act1:
                 st.markdown('<div class="bounce-guide">👇 클릭하여 확인</div>', unsafe_allow_html=True)
                 if st.button("📄 기획서 보기", type="primary", use_container_width=True):
                     show_plan_dialog()
             with col_act2:
                 if st.button("🔍 AI 분석 데이터 (설계도)", use_container_width=True):
                     show_analysis_dialog()

             # 실행 과정 시각화
             with st.expander("📊 실행 과정 상세 보기", expanded=False):
                 hist = state.get("step_history", [])
                 render_visual_timeline(hist)

             render_refinement_ui()

    # [MOVED] 상태 표시기 위치는 더 아래로 이동됨


    # =========================================================================
    # 하단 입력 영역
    # =========================================================================
    st.markdown("---")
    with st.expander("📎 참고 자료 추가 (파일 업로드)", expanded=False):
        # 파일 업로드 보안 설정
        MAX_FILE_SIZE_MB = 10
        MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
        ALLOWED_EXTENSIONS = {"txt", "md", "docx", "pdf"}

        uploaded_file = st.file_uploader(
            "기획서 생성에 참고할 파일 (PDF, DOCX, TXT 등)",
            type=["txt", "md", "docx", "pdf"],
            key="file_uploader_bottom"
        )
        if uploaded_file:
            try:
                # 1. 파일 크기 검증
                file_size = len(uploaded_file.getbuffer())
                if file_size > MAX_FILE_SIZE_BYTES:
                    st.error(f"파일이 너무 큽니다. 최대 {MAX_FILE_SIZE_MB}MB까지 허용됩니다.")
                # 2. 파일명 검증 (경로 조회 방지)
                elif ".." in uploaded_file.name or "/" in uploaded_file.name or "\\" in uploaded_file.name:
                    st.error("유효하지 않은 파일명입니다.")
                # 3. 확장자 재검증
                elif not uploaded_file.name.split(".")[-1].lower() in ALLOWED_EXTENSIONS:
                    st.error("지원하지 않는 파일 형식입니다.")
                else:
                    content = uploaded_file.read().decode("utf-8", errors='ignore')
                    # 4. 콘텐츠 길이 제한 (50,000자)
                    if len(content) > 50000:
                        content = content[:50000]
                        st.warning("파일이 너무 길어 일부만 사용됩니다 (50,000자 제한)")
                    st.session_state.uploaded_content = content
                    st.success(f"✅ '{uploaded_file.name}' 업로드됨 ({file_size // 1024}KB)")
            except Exception as e:
                st.error("파일을 읽을 수 없습니다. 파일 형식을 확인해주세요.")

    # Prefill 확인 UI
    if st.session_state.prefill_prompt and not st.session_state.pending_input:
        st.info(f"📝 **선택된 예시:** {st.session_state.prefill_prompt}")
        col_ok, col_no = st.columns([1, 1])
        with col_ok:
            if st.button("✅ 이대로 시작", use_container_width=True):
                user_msg = st.session_state.prefill_prompt
                st.session_state.prefill_prompt = None
                st.session_state.chat_history.append({"role": "user", "content": user_msg, "type": "text"})
                st.session_state.pending_input = user_msg
                st.rerun()
        with col_no:
            if st.button("❌ 취소", use_container_width=True):
                st.session_state.prefill_prompt = None
                st.rerun()

    # =========================================================================
    # [UX] 상태 표시기를 위한 Placeholder 위치 (채팅 입력창 바로 위!)
    # =========================================================================
    st.markdown("<div style='margin-bottom: 0.5rem;'></div>", unsafe_allow_html=True)
    status_placeholder = st.empty()


    # 채팅 입력창
    placeholder_text = "💬 자유롭게 대화를 입력하세요..."
    if st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
        placeholder_text = "💬 위 옵션을 선택하거나, 다른 의견을 직접 입력하세요..."

    user_input = st.chat_input(placeholder_text, key=f"chat_input_{st.session_state.input_key}")

    if user_input:
        st.session_state.prefill_prompt = None
        st.session_state.chat_history.append({"role": "user", "content": user_input, "type": "text"})
        st.session_state.input_key += 1
        st.session_state.pending_input = user_input
        st.rerun()
        
    
    # =========================================================================
    # 2. 실행 로직 (Start or Resume) [맨 아래에서 실행, 렌더링은 Placeholder로]
    # =========================================================================
    if st.session_state.pending_input:
        pending_text = st.session_state.pending_input
        st.session_state.pending_input = None
        
        # 1. Resume Command 파싱
        resume_cmd = None
        import json
        
        if pending_text.startswith("FORM_DATA:"):
            try:
                form_data = json.loads(pending_text.replace("FORM_DATA:", ""))
                resume_cmd = {"resume": form_data}
            except (json.JSONDecodeError, ValueError):
                from ui.validation import show_validation_error, ValidationErrorType
                show_validation_error(ValidationErrorType.INVALID_FORMAT, "폼 데이터를 확인해주세요")
        elif pending_text.startswith("OPTION:"):
            try:
                option_data = json.loads(pending_text.replace("OPTION:", ""))
                resume_cmd = {"resume": {"selected_option": option_data}}
            except (json.JSONDecodeError, ValueError):
                from ui.validation import show_validation_error, ValidationErrorType
                show_validation_error(ValidationErrorType.INVALID_FORMAT, "선택 데이터를 확인해주세요")
        elif st.session_state.current_state and st.session_state.current_state.get("__interrupt__"):
            resume_cmd = {"resume": {"text_input": pending_text}}
        elif st.session_state.current_state and st.session_state.current_state.get("need_more_info"):
            resume_cmd = {"resume": {"text_input": pending_text}}
            
        # 2. 워크플로우 실행
        from utils.streamlit_callback import StreamlitStatusCallback
        
        # [UX] 상태 표시기를 미리 확보한 위치(Placeholder)에 배치
        with status_placeholder.container():
            with st.status("🚀 작업을 수행하고 있습니다...", expanded=True) as status:
                try:
                    streamlit_callback = StreamlitStatusCallback(status)
                    file_content = st.session_state.get("uploaded_content", None)
                    current_refine_count = st.session_state.get("next_refine_count", 0)
                    previous_plan = st.session_state.generated_plan
                    
                    final_result = run_plancraft(
                        user_input=pending_text,
                        file_content=file_content,
                        refine_count=current_refine_count,
                        previous_plan=previous_plan,
                        callbacks=[streamlit_callback],
                        thread_id=st.session_state.thread_id,
                        resume_command=resume_cmd,
                        generation_preset=st.session_state.get("generation_preset", "balanced")
                    )
                    
                    status.update(label="✅ 처리 완료!", state="complete", expanded=False)

                    # 3. 결과 State 저장
                    st.session_state.current_state = final_result
                    if current_refine_count > 0:
                         final_result["refine_count"] = current_refine_count
                         st.session_state.next_refine_count = 0

                    # 4. 결과 처리 로직 (잡담 vs 기획서 vs 추가질문)
                    analysis_res = final_result.get("analysis")
                    generated_plan = final_result.get("final_output", "")
                    
                    # [FIX] 인터럽트 페이로드(Payload) 우선 확인 (Multi-HITL 지원)
                    interrupt_data = final_result.get("__interrupt__")
                    
                    # 상태값 초기화
                    need_more_info = final_result.get("need_more_info", False)
                    options = final_result.get("options", [])
                    option_question = final_result.get("option_question", "다음과 같이 기획 방향을 제안합니다.")
                    
                    # 인터럽트가 있으면 Payload 데이터로 덮어쓰기
                    if interrupt_data:
                        # Payload 구조: { "question": "...", "options": [...] }
                        if "question" in interrupt_data:
                            option_question = interrupt_data["question"]
                        if "options" in interrupt_data:
                            options = interrupt_data["options"]
                        # 인터럽트는 항상 사용자 응답 대기 상태임
                        need_more_info = True

                    is_general = False
                    if analysis_res and isinstance(analysis_res, dict):
                        is_general = analysis_res.get("is_general_query", False)

                    # [FIX] options가 있으면 무조건 기획 제안 모드로 처리 (옵션 우선!)
                    if options and len(options) > 0 and not is_general:
                        # B. 기획 제안 & 미리보기 표시
                        # q = option_question # 위에서 설정됨

                        preview_msg = ""
                        # [FIX] Analyzer가 증폭한 컨셉 정보 항상 표시 (interrupt 유무와 무관)
                        if analysis_res:
                            p_topic = analysis_res.get("topic", "미정")
                            p_purpose = analysis_res.get("purpose", "")
                            p_features = analysis_res.get("key_features", [])

                            preview_msg += f"**📌 제안 컨셉**: {p_topic}\n"
                            preview_msg += f"**🎯 기획 의도**: {p_purpose}\n"
                            if p_features:
                                feats = ", ".join(p_features[:4])
                                preview_msg += f"**💡 주요 기능**: {feats} 등\n"
                            preview_msg += "\n"

                        # Markdown 충돌 방지를 위해 option_question은 있는 그대로 출력 (Bold 제거)
                        msg = f"🤔 {option_question}\n\n{preview_msg}"
                        msg_content = msg
                        for o in options:
                            msg_content += f"- **{o.get('title')}**: {o.get('description')}\n"

                        st.session_state.chat_history.append({"role": "assistant", "content": msg_content, "type": "options"})

                    elif is_general:
                        # A. 일반 대화 응답
                        ans = analysis_res.get("general_answer", "무엇을 도와드릴까요?")
                        st.session_state.chat_history.append({"role": "assistant", "content": ans, "type": "text"})
                        st.session_state.generated_plan = None 

                    elif generated_plan:
                        # C. 기획서 완성
                        st.session_state.generated_plan = generated_plan
                        
                        # [NEW] 토큰 사용량 정보 수집
                        usage_info = ""
                        if hasattr(streamlit_callback, 'get_usage_summary'):
                            usage = streamlit_callback.get_usage_summary()
                            if usage.get("total_tokens", 0) > 0:
                                # 프리셋 정보 가져오기
                                from utils.settings import get_preset
                                preset_key = st.session_state.get("generation_preset", "balanced")
                                preset = get_preset(preset_key)
                                
                                usage_info = f"\n\n---\n🤖 **사용 모델**: {preset.model_type} ({preset.name})\n📊 **토큰 사용량**: {usage['total_tokens']:,}개 (입력: {usage['input_tokens']:,}, 출력: {usage['output_tokens']:,})\n💰 **예상 비용**: ${usage['estimated_cost_usd']:.4f} (약 {int(usage['estimated_cost_krw'])}원)"
                        
                        st.session_state.chat_history.append({
                            "role": "assistant", 
                            "content": f"✅ 기획서가 완성되었습니다!{usage_info}", 
                            "type": "plan"
                        })
                        
                        st.session_state.trigger_notification = True
                        
                        now_str = datetime.now().strftime("%H:%M:%S")
                        if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
                             st.session_state.plan_history.append({
                                "version": len(st.session_state.plan_history) + 1, "timestamp": now_str, "content": generated_plan
                             })

                        chat_summary = final_result.get("chat_summary", "")
                        if chat_summary:
                             st.session_state.chat_history.append({"role": "assistant", "content": chat_summary, "type": "summary"})

                        # [NEW] Mermaid 다이어그램 자동 생성 및 표시 (Supervisor 실행 결과 시각화)
                        # Supervisor의 실행 계획(_plan) 정보를 기반으로 Mermaid 그래프 생성
                        if final_result.get("_plan"):
                            from agents.agent_config import export_plan_to_mermaid
                            mermaid_code = export_plan_to_mermaid(final_result["_plan"])
                            if mermaid_code:
                                with st.expander("🔗 실행 계획 다이어그램 (Mermaid)", expanded=True):
                                     from ui.components import render_scalable_mermaid
                                     render_scalable_mermaid(mermaid_code, height=400)
                                     st.caption("Supervisor가 수립하고 실행한 에이전트 협업 구조도입니다.")

                    else:
                        st.session_state.chat_history.append({"role": "assistant", "content": "작업이 완료되었습니다.", "type": "text"})

                    st.rerun()
                    
                except Exception as e:
                    import traceback
                    from ui.validation import handle_exception_friendly, detect_error_type, ERROR_MESSAGES

                    # 친화적인 에러 메시지 표시
                    handle_exception_friendly(e, context="기획서 생성 중")

                    # 상태 업데이트
                    if st.session_state.current_state:
                         if isinstance(st.session_state.current_state, dict):
                             st.session_state.current_state.update({"error": str(e), "step_status": "FAILED"})

                    # 채팅 히스토리에 친화적 메시지 추가
                    error_type = detect_error_type(e)
                    error_info = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES[error_type.UNKNOWN])
                    friendly_msg = f"{error_info['icon']} **{error_info['title']}**\n\n{error_info['message']}\n\n{error_info['hint']}"

                    st.session_state.chat_history.append({
                        "role": "assistant", "content": friendly_msg, "type": "error"
                    })


# =============================================================================
# 메인 함수
# =============================================================================
def main():
    """메인 함수"""
    # 1. 리소스 초기화 (RAG, Config 등) - 실패해도 앱 실행 보장
    init_resources()
    
    # 2. 세션 초기화
    init_session_state()
    
    # [NEW] Modal Action 처리 (UI Component에서 넘어온 요청)
    # [MOVED] Modal Action Logic Removed (Structure Approval Deprecated)
    
    # 3. 메인 UI 렌더링
    render_main()


if __name__ == "__main__":
    main()
