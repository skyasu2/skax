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
    render_refinement_ui,
    render_error_state,
    render_option_selector,
    render_visual_timeline,
    render_human_interaction  # [NEW]
)

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
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 8rem;
    }

    .result-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }

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

    .stChatInput {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 1rem 1rem 2rem 1rem;
        background: linear-gradient(to top, #ffffff 90%, rgba(255,255,255,0));
        z-index: 1000;
        border-top: none;
    }

    .stChatInput > div {
        max-width: 800px;
        margin: 0 auto;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        border-radius: 28px;
    }

    .stChatInput textarea {
        border-radius: 28px !important;
        border: 1px solid #e0e0e0 !important;
        padding: 14px 24px !important;
        font-size: 1rem !important;
        background-color: #ffffff !important;
    }

    .stChatInput textarea:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2) !important;
    }
    
    .stChatInput div[data-baseweb="textarea"] {
        background-color: transparent !important;
        border: none !important;
    }
    
    .stChatInput div[data-baseweb="base-input"] {
         background-color: transparent !important;
    }

    .stChatInput button[kind="primary"] {
        border-radius: 50% !important;
        width: 40px !important;
        height: 40px !important;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
        color: white !important;
        right: 10px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
    }

    .stChatInput button[kind="primary"]:hover {
        opacity: 0.9;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
    }
    
    .stChatInput button[kind="primary"] svg {
        width: 18px !important;
        height: 18px !important;
    }
</style>
""", unsafe_allow_html=True)


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


# =============================================================================
# 메인 렌더링
# =============================================================================
def render_main():
    """메인 영역 렌더링"""
    # =========================================================================
    # 헤더
    # =========================================================================
    col_title, col_menu = st.columns([6, 1])

    with col_title:
        st.markdown("### 📋 PlanCraft Agent")
    
    with col_menu:
        with st.popover("메뉴"):
            st.caption("PlanCraft v2.1")
            
            if st.button("🆕 새 대화 시작", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.current_state = None
                st.session_state.generated_plan = None
                st.session_state.input_key += 1
                st.session_state.thread_id = str(uuid.uuid4())
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
        st.markdown(
            """
            <div style="text-align: center; margin-top: 0vh; margin-bottom: 1.5rem;">
                <h1>💡 무엇을 도와드릴까요?</h1>
                <p style="color: #666; font-size: 1rem; line-height: 1.5;">
                    <b>PlanCraft AI</b>가 아이디어를 구체적인 기획서로 만들어 드립니다.<br>
                    웹 서비스, 앱, 창업, 사업계획서 등 무엇이든 물어보세요.
                </p>
                <div style="margin-top: 0.8rem; color: #888; font-size: 0.85rem;">
                    👇 아래 <b>채팅창</b>에 입력하거나, 추천 <b>예시</b>를 선택하세요.
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # 예제 데이터 로드 (랜덤)
        if "random_examples" not in st.session_state or st.session_state.random_examples is None:
             from utils.prompt_examples import WEB_APP_POOL, NON_IT_POOL
             st.session_state.random_examples = random.sample(WEB_APP_POOL, 1) + random.sample(NON_IT_POOL, 2)

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
    # =========================================================================
    # 1. 사용자 채팅 입력 처리
    # =========================================================================
    if prompt := st.chat_input("기획 요청사항을 입력하세요..."):
        # prefill이 있으면 초기화
        st.session_state.prefill_prompt = None
        
        # 사용자 메시지 히스토리에 추가
        st.session_state.chat_history.append({"role": "user", "content": prompt, "type": "text"})
        st.session_state.input_key += 1
        
        # 실행 대기열에 등록
        st.session_state.pending_input = prompt
        st.rerun()

    # =========================================================================
    # 2. 실행 로직 (Start or Resume)
    # =========================================================================
    if st.session_state.pending_input:
        pending_text = st.session_state.pending_input
        st.session_state.pending_input = None
        
        # Resume Command 여부 확인
        resume_cmd = None
        import json
        
        # 폼 데이터 (JSON)
        if pending_text.startswith("FORM_DATA:"):
            try:
                form_data = json.loads(pending_text.replace("FORM_DATA:", ""))
                resume_cmd = {"resume": form_data}
            except:
                st.error("입력 데이터 처리 중 오류 발생")
        # 옵션 선택 (JSON)
        elif pending_text.startswith("OPTION:"):
            try:
                option_data = json.loads(pending_text.replace("OPTION:", ""))
                resume_cmd = {"resume": {"selected_option": option_data}}
            except:
                resume_cmd = {"resume": {"text_input": pending_text}}
        # 일반 텍스트이면서 인터럽트 상태일 때 -> Resume로 간주
        elif st.session_state.current_state and st.session_state.current_state.get("__interrupt__"):
            resume_cmd = {"resume": {"text_input": pending_text}}
        else:
             # 일반 시작
             pass

        from utils.streamlit_callback import StreamlitStatusCallback
        
        with st.chat_message("assistant"):
            with st.status("🚀 작업을 수행하고 있습니다...", expanded=True) as status:
                try:
                    streamlit_callback = StreamlitStatusCallback(status)
                    file_content = st.session_state.get("uploaded_content", None)
                    current_refine_count = st.session_state.get("next_refine_count", 0)
                    previous_plan = st.session_state.generated_plan
                    
                    # user_input은 새로 시작할 때만 유효, resume시는 무시됨(하지만 함수 인자로는 전달)
                    final_state_dict = run_plancraft(
                        user_input=pending_text, 
                        file_content=file_content,
                        refine_count=current_refine_count,
                        previous_plan=previous_plan,
                        callbacks=[streamlit_callback],
                        thread_id=st.session_state.thread_id,
                        resume_command=resume_cmd
                    )
                    
                    status.update(label="✅ 처리 완료!", state="complete", expanded=False)
                    
                    # 결과 저장
                    st.session_state.current_state = final_state_dict
                    if current_refine_count > 0:
                         final_state_dict["refine_count"] = current_refine_count
                         st.session_state.next_refine_count = 0

                    st.rerun()
                    
                except Exception as e:
                    import traceback
                    st.error(f"실행 중 오류가 발생했습니다: {str(e)}")
                    st.code(traceback.format_exc())
                    
                    # 에러 상태 저장
                    if st.session_state.current_state:
                         if isinstance(st.session_state.current_state, dict):
                             st.session_state.current_state.update({"error": str(e), "step_status": "FAILED"})

                    st.session_state.chat_history.append({
                        "role": "assistant", "content": f"❌ 오류 발생: {str(e)}", "type": "error"
                    })

    # =========================================================================
    # 3. 화면 렌더링 (히스토리 & 현재 상태 UI)
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
            # UI 렌더러 호환성 위해 로컬 state 변수 업데이트
            # (실제 state 객체를 수정하진 않음)
            ui_state = state.copy() 
            ui_state.update({
                "input_schema_name": payload.get("input_schema_name"),
                "options": payload.get("options"),
                "option_question": payload.get("question"),
                "need_more_info": True
            })
            render_human_interaction(ui_state)
            
        # C. 기존 방식 호환 (need_more_info 플래그)
        elif state.get("need_more_info"):
            render_human_interaction(state)
            
        # D. 최종 결과
        elif state.get("final_output"):
             st.success("기획서 작성이 완료되었습니다!")
             st.session_state.generated_plan = state["final_output"]
             
             # 히스토리 중복 방지 (가장 마지막이 plan타입이면 생략 등)
             if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != state["final_output"]:
                 now_str = datetime.now().strftime("%H:%M:%S")
                 st.session_state.plan_history.append({
                    "version": len(st.session_state.plan_history) + 1,
                    "timestamp": now_str,
                    "content": state["final_output"]
                 })

             with st.expander("📄 최종 기획서 보기", expanded=True):
                 st.markdown(state["final_output"])
                 
             col1, col2 = st.columns(2)
             if col1.button("✨ 다시 개선하기"):
                 st.session_state.next_refine_count = st.session_state.current_state.get("refine_count", 0) + 1
                 st.session_state.pending_input = "이 내용을 바탕으로 더 구체적으로 보완해줘"
                 st.rerun()

    # =========================================================================
    # 4. 사이드바 (워크플로우 시각화)
    # =========================================================================
    with st.sidebar:
        if st.session_state.current_state:
            hist = st.session_state.current_state.get("step_history", [])
            render_visual_timeline(hist)
            
            st.markdown("---")
            
            # 사이드바 액션 버튼들
            c1, c2 = st.columns(2)
            if c1.button("📖 기획서", use_container_width=True):
                 show_plan_dialog()
            if c2.button("🔍 분석", use_container_width=True):
                 show_analysis_dialog()
                 
            # 다운로드
            if st.session_state.generated_plan:
                 st.download_button(
                    "📥 저장 (.md)",
                    data=st.session_state.generated_plan,
                    file_name=f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
                 
            render_refinement_ui()

    # =========================================================================
    # 하단 입력 영역
    # =========================================================================
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

    # 채팅 입력창
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
                    thread_id=st.session_state.thread_id
                )
                
                status.update(label="✅ 과정 완료!", state="complete", expanded=False)
                st.session_state.current_state = final_result

                if current_refine_count > 0:
                     final_result["refine_count"] = current_refine_count
                     st.session_state.next_refine_count = 0

                # 결과 처리
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
                    
                    now_str = datetime.now().strftime("%H:%M:%S")
                    new_version = len(st.session_state.plan_history) + 1
                    
                    if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
                         st.session_state.plan_history.append({
                            "version": new_version, "timestamp": now_str, "content": generated_plan
                         })

                    chat_summary = final_result.get("chat_summary", "")
                    if chat_summary:
                        st.session_state.chat_history.append({"role": "assistant", "content": chat_summary, "type": "summary"})
                
                else:
                    ans = "죄송합니다, 적절한 응답을 생성하지 못했습니다."
                    if analysis_res:
                         if isinstance(analysis_res, dict):
                             ans = analysis_res.get("general_answer", ans)
                         elif hasattr(analysis_res, "general_answer"):
                             ans = getattr(analysis_res, "general_answer", ans)
                    st.session_state.chat_history.append({"role": "assistant", "content": ans, "type": "text"})

            except Exception as e:
                # [NEW] State에도 에러 기록 (Fallback UI용)
                if st.session_state.current_state:
                     # Pydantic 모델인 경우
                     if hasattr(st.session_state.current_state, "model_copy"):
                         st.session_state.current_state = st.session_state.current_state.model_copy(update={
                             "error": str(e),
                             "step_status": "FAILED"
                         })
                
                st.session_state.chat_history.append({
                    "role": "assistant", "content": f"❌ 오류 발생: {str(e)}", "type": "error"
                })
        
        st.rerun()


# =============================================================================
# 환경 체크
# =============================================================================
def check_environment():
    """실행 환경 및 의존성 체크 (자동 초기화)"""
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


# =============================================================================
# 메인 함수
# =============================================================================
def main():
    """메인 함수"""
    check_environment()
    init_session_state()
    render_main()


if __name__ == "__main__":
    main()
