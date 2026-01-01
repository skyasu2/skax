"""
UI Components Module

재사용 가능한 UI 컴포넌트들을 정의합니다.
"""

import streamlit as st
import streamlit.components.v1 as components
from ui.dynamic_form import render_pydantic_form  # [NEW]
  # [NEW] HTML 컴포넌트용


def render_mermaid(code: str, height: int = 400):
    """Mermaid 다이어그램 렌더링"""
    components.html(
        f"""
        <div class="mermaid">
            {code}
        </div>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
        </script>
        """,
        height=height,
        scrolling=True
    )


def render_visual_timeline(step_history: list):
    """
    실행 이력 시각화 (텍스트 타임라인)
    """
    if not step_history:
        return

    # 텍스트 기반 타임라인 (안정적)
    render_timeline(step_history)

    # (선택) 원본 데이터 보기
    with st.expander("📊 원본 JSON 데이터 (Debug)", expanded=False):
         st.json(step_history)


def render_progress_steps(current_step: str = None):
    """
    진행 상태 표시 (개선된 버전)

    - Streamlit 프로그레스 바 추가
    - CSS 변수 활용
    - 단계별 설명 표시
    """
    steps = ["📥 분석", "🏗️ 구조", "✍️ 작성", "🔍 검토", "✨ 개선", "📋 완료"]
    step_keys = ["analyze", "structure", "write", "review", "refine", "format"]
    step_descriptions = {
        "analyze": "사용자의 요구사항을 분석하고 있습니다...",
        "structure": "기획서의 구조를 설계하고 있습니다...",
        "write": "섹션별 내용을 작성하고 있습니다...",
        "review": "품질을 검토하고 있습니다...",
        "refine": "피드백을 반영하여 개선하고 있습니다...",
        "format": "최종 문서를 정리하고 있습니다..."
    }

    current_idx = -1
    if current_step:
        for i, key in enumerate(step_keys):
            if key in current_step.lower():
                current_idx = i
                break

    # 프로그레스 바 (0~1 사이 값)
    if current_idx >= 0:
        progress_value = (current_idx + 1) / len(steps)
        st.progress(progress_value, text=f"진행률: {int(progress_value * 100)}% ({current_idx + 1}/{len(steps)} 단계)")

    # 단계별 아이콘 표시
    cols = st.columns(len(steps))
    for i, (step, key) in enumerate(zip(steps, step_keys)):
        with cols[i]:
            icon = step.split()[0]  # 이모지 추출
            label = step.split()[1] if len(step.split()) > 1 else ""

            if i < current_idx:
                # 완료된 단계
                st.markdown(
                    f"<div style='text-align:center; color:var(--color-success, #28a745);'>"
                    f"<div style='font-size:1.5rem;'>{icon}</div>"
                    f"<small>✅ {label}</small></div>",
                    unsafe_allow_html=True
                )
            elif i == current_idx:
                # 현재 단계 (강조)
                st.markdown(
                    f"<div style='text-align:center; color:var(--color-primary, #667eea); font-weight:bold;'>"
                    f"<div style='font-size:1.8rem;'>{icon}</div>"
                    f"<small>▶️ {label}</small></div>",
                    unsafe_allow_html=True
                )
            else:
                # 대기 단계
                st.markdown(
                    f"<div style='text-align:center; color:var(--color-text-disabled, #ccc);'>"
                    f"<div style='font-size:1.2rem;'>{icon}</div>"
                    f"<small>{label}</small></div>",
                    unsafe_allow_html=True
                )

    # 현재 단계 설명
    if current_step and current_step in step_descriptions:
        st.markdown(
            f"<div style='text-align:center; color:var(--color-text-muted, #666); "
            f"font-size:0.9rem; margin-top:1rem; background-color:var(--color-bg-light, #f8f9fa); "
            f"padding:0.75rem; border-radius:var(--radius-sm, 8px); border-left:3px solid var(--color-primary, #667eea);'>"
            f"💬 {step_descriptions[current_step]}</div>",
            unsafe_allow_html=True
        )


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


def render_error_state(current_state):
    """
    [개선] 에러 상태 UI 렌더링
    
    에러 메시지를 명확히 표시하고, 스마트한 복구 옵션을 제공합니다.
    """
    if not current_state:
        return

    error_msg = current_state.get("error_message") or current_state.get("error") or "알 수 없는 오류 발생"
    retry_count = current_state.get("retry_count", 0)

    st.error(f"### 🚫 오류 발생 (Retry: {retry_count})\n\n{error_msg}")
    
    with st.expander("상세 정보 보기", expanded=False):
        st.json(current_state)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 다시 시도", type="primary", use_container_width=True):
            # 상태 초기화 후 재시도 (재시도 카운트 증가)
            # 여기서는 단순히 세션 상태를 업데이트하고 rerun 합니다.
            # 실제 복구 로직은 App의 재실행 흐름에 맡깁니다.
            if st.session_state.current_state:
                st.session_state.current_state["retry_count"] = retry_count + 1
                st.session_state.current_state["error"] = None
                st.session_state.current_state["error_message"] = None
                st.session_state.current_state["step_status"] = "RUNNING"
            st.rerun()
            
    with col2:
        if st.button("✏️ 처음으로 돌아가기", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.current_state = None
            st.session_state.generated_plan = None
            st.rerun()


def render_human_interaction(current_state):
    """
    [통합] 휴먼 인터럽트 UI 렌더링
    
    1. 스키마 기반 폼 (input_schema가 있는 경우)
    2. 옵션 선택 버튼 (options가 있는 경우)
    3. 일반 텍스트 입력 (Fallback)
    """
    if not current_state:
        return

    # =========================================================================
    # [NEW] 에러 메시지 표시 개선 (HITL 재시도 시 명확한 피드백)
    # =========================================================================
    error_msg = current_state.get("error")
    retry_count = current_state.get("retry_count", 0)
    
    if error_msg:
        # 에러 유형에 따른 아이콘 및 안내 메시지
        error_icon = "⚠️"
        error_hint = "다시 시도해 주세요."
        
        if "필수" in str(error_msg) or "누락" in str(error_msg):
            error_icon = "📋"
            error_hint = "필수 항목을 모두 입력해 주세요."
        elif "형식" in str(error_msg) or "유효" in str(error_msg):
            error_icon = "📝"
            error_hint = "올바른 형식으로 입력해 주세요."
        elif "선택" in str(error_msg):
            error_icon = "👆"
            error_hint = "아래 옵션 중 하나를 선택해 주세요."
        
        # 재시도 횟수 표시 (최대 횟수 경고)
        MAX_RETRIES = 5
        retry_info = ""
        if retry_count > 0:
            remaining = MAX_RETRIES - retry_count
            if remaining <= 2:
                retry_info = f" 🔄 (남은 시도: {remaining}회)"
            else:
                retry_info = f" (시도 {retry_count}/{MAX_RETRIES})"
        
        # 에러 메시지 박스 렌더링
        st.markdown(f"""
        <div style="
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-left: 4px solid #fd7e14;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 16px;
        ">
            <strong>{error_icon} 입력 오류{retry_info}</strong>
            <p style="margin: 8px 0 0 0; color: #856404;">{error_msg}</p>
            <small style="color: #6c757d;">💡 {error_hint}</small>
        </div>
        """, unsafe_allow_html=True)

    # 1. Schema-driven Form (Priority)
    # PlanCraftState에 저장된 스키마 클래스명(Str)을 이용해 동적으로 폼 생성
    schema_name = current_state.get("input_schema_name")
    if schema_name:
        from utils import schemas
        model_cls = getattr(schemas, schema_name, None)
        
        if model_cls:
            st.markdown(f"##### 📝 추가 정보 입력 ({model_cls.__name__})")
            form_data = render_pydantic_form(model_cls, key_prefix="interrupt_form")
            
            if form_data:
                # 폼 제출 처리
                st.session_state.chat_history.append({
                    "role": "user", "content": f"[폼 입력 제출]\\n{form_data}", "type": "text"
                })
                # JSON 형태로 pending_input 저장
                import json
                st.session_state.current_state = None
                st.session_state.pending_input = f"FORM_DATA:{json.dumps(form_data, ensure_ascii=False)}"
                st.rerun()
            return

    # 2. Option Selector
    if current_state.get("options"):
        render_option_selector(current_state)
        return

    # 3. Fallback (If any other interrupt without options)
    st.info("사용자 입력 대기 중...")


def render_option_selector(current_state):
    """
    옵션 선택 UI 렌더링 (휴먼 인터럽트)
    
    Pydantic 스키마(OptionChoice) 기반의 옵션 목록을 렌더링하고,
    사용자 선택을 처리합니다.
    """
    if not current_state:
        return

    from graph.state import safe_get

    # TypedDict dict-access 방식으로 통일
    options = current_state.get("options", [])
    if not options:
        return

    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        # dict 또는 Pydantic 객체 모두 지원
        title = safe_get(opt, "title", "")
        description = safe_get(opt, "description", "")

        with cols[i]:
            if st.button(f"{title}", key=f"opt_{i}", use_container_width=True, help=description):
                # 선택 처리 로직
                st.session_state.chat_history.append({
                    "role": "user", "content": f"'{title}' 선택", "type": "text"
                })

                # 입력 구성 (dict-access)
                original_input = current_state.get("user_input", "")
                new_input = f"{original_input}\n\n[선택: {title} - {description}]"

                # 상태 업데이트 및 재실행 준비
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


def trigger_browser_notification(title: str, body: str):
    """
    브라우저 알림(Notification API)을 트리거합니다.
    Streamlit 환경에서 JS를 주입합니다.
    """
    js_code = f"""
    <script>
    (function() {{
        function notify() {{
            if (!("Notification" in window)) {{
                console.log("This browser does not support desktop notification");
                return;
            }}
            
            if (Notification.permission === "granted") {{
                new Notification("{title}", {{ body: "{body}" }});
            }} else if (Notification.permission !== "denied") {{
                Notification.requestPermission().then(function (permission) {{
                    if (permission === "granted") {{
                        new Notification("{title}", {{ body: "{body}" }});
                    }}
                }});
            }}
        }}
        // DOM 로드 안정화 후 실행
        setTimeout(notify, 1000);
    }})();
    </script>
    """
    components.html(js_code, height=0, width=0)


# render_structure_dialog has been removed since Structure Approval step is deprecated.

