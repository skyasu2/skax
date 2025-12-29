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
from ui.styles import CUSTOM_CSS

# =============================================================================
# CSS 스타일
# =============================================================================
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
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

        # 예제 데이터 로드 (초기: Static, 변경: AI)
        if "random_examples" not in st.session_state or st.session_state.random_examples is None:
             from utils.prompt_examples import WEB_APP_POOL, NON_IT_POOL
             st.session_state.random_examples = random.sample(WEB_APP_POOL, 1) + random.sample(NON_IT_POOL, 2)

        col_ex_head, col_ex_refresh = st.columns([5, 1], vertical_alignment="bottom")
        with col_ex_head:
            st.markdown("#### 🎲 AI 브레인스토밍 (추천 아이디어)")
        with col_ex_refresh:
            if st.button("🔄 AI 생성", key="refresh_hero_ex", help="AI가 실시간으로 새로운 아이디어를 제안합니다"):
                from utils.idea_generator import generate_creative_ideas
                with st.spinner("💡 아이디어를 떠올리는 중..."):
                    st.session_state.random_examples = generate_creative_ideas(3)
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
        
        # 1. Resume Command 파싱
        resume_cmd = None
        import json
        
        if pending_text.startswith("FORM_DATA:"):
            try:
                form_data = json.loads(pending_text.replace("FORM_DATA:", ""))
                resume_cmd = {"resume": form_data}
            except:
                st.error("입력 데이터 처리 중 오류 발생")
        elif pending_text.startswith("OPTION:"):
            try:
                option_data = json.loads(pending_text.replace("OPTION:", ""))
                resume_cmd = {"resume": {"selected_option": option_data}}
            except:
                resume_cmd = {"resume": {"text_input": pending_text}}
        elif st.session_state.current_state and st.session_state.current_state.get("__interrupt__"):
            resume_cmd = {"resume": {"text_input": pending_text}}
            
        # 2. 워크플로우 실행
        from utils.streamlit_callback import StreamlitStatusCallback
        
        with st.chat_message("assistant"):
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
                        resume_command=resume_cmd
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
                    need_more_info = final_result.get("need_more_info", False)
                    options = final_result.get("options", [])

                    # [Check] 일반 잡담 여부 확인
                    is_general = False
                    if analysis_res and isinstance(analysis_res, dict):
                        is_general = analysis_res.get("is_general_query", False)

                    # [DEBUG] 플래그 값 출력
                    print(f"[DEBUG] app.py - is_general: {is_general}, need_more_info: {need_more_info}")
                    print(f"[DEBUG] app.py - options count: {len(options)}")

                    # [FIX] options가 있으면 무조건 기획 제안 모드로 처리 (옵션 우선!)
                    if options and len(options) > 0 and not is_general:
                        # B. 기획 제안 & 미리보기 표시 (옵션 버튼 있는 경우)
                        q = final_result.get("option_question", "다음과 같이 기획 방향을 제안합니다.")
                        
                        # [UX] 제안 내용 미리보기 구성
                        preview_msg = ""
                        if analysis_res:
                            p_topic = analysis_res.get("topic", "미정")
                            p_purpose = analysis_res.get("purpose", "")
                            p_features = analysis_res.get("key_features", [])
                            
                            preview_msg += f"**📌 제안 컨셉**: {p_topic}\n"
                            if p_purpose:
                                preview_msg += f"**🎯 기획 의도**: {p_purpose}\n"
                            if p_features:
                                feats = ", ".join(p_features[:4])
                                preview_msg += f"**💡 주요 기능**: {feats} 등\n"
                            preview_msg += "\n"

                        msg_content = f"🤔 **{q}**\n\n{preview_msg}"
                        
                        # 옵션 설명 추가
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
                        st.session_state.chat_history.append({"role": "assistant", "content": "✅ 기획서가 완성되었습니다!", "type": "plan"})
                        
                        # [NEW] 알림 예약 (Rerun 후 실행됨)
                        st.session_state.trigger_notification = True
                        
                        now_str = datetime.now().strftime("%H:%M:%S")
                        if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
                             st.session_state.plan_history.append({
                                "version": len(st.session_state.plan_history) + 1, "timestamp": now_str, "content": generated_plan
                             })

                        chat_summary = final_result.get("chat_summary", "")
                        if chat_summary:
                             st.session_state.chat_history.append({"role": "assistant", "content": chat_summary, "type": "summary"})
                    
                    else:
                        # D. 기타 (분석 단계 등)
                        st.session_state.chat_history.append({"role": "assistant", "content": "작업이 완료되었습니다.", "type": "text"})

                    st.rerun()
                    
                except Exception as e:
                    import traceback
                    st.error(f"실행 중 오류가 발생했습니다: {str(e)}")
                    st.code(traceback.format_exc())
                    
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
        elif state.get("final_output") and not state.get("analysis", {}).get("is_general_query", False):
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

             # 실행 과정 시각화 (메인 통합)
             with st.expander("📊 실행 과정 상세 보기", expanded=False):
                 hist = state.get("step_history", [])
                 render_visual_timeline(hist)

             render_refinement_ui()

    # =========================================================================
    # 4. 사이드바 (워크플로우 시각화)
    # =========================================================================

                 
    

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
    # (Cleanup) 하단 중복 로직 제거 완료



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
