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
    실행 이력을 Mermaid Flowchart로 시각화
    
    분기, 루프, 상태(성공/실패)를 그래프 형태로 보여줍니다.
    """
    if not step_history:
        return

    # Mermaid 코드 생성 시작
    mermaid_code = ["graph TD"]
    mermaid_code.append("    Start((Start))")
    
    last_node_id = "Start"
    
    for i, item in enumerate(step_history):
        step = item.get("step", "").replace(" ", "_").replace("-", "_")
        status = item.get("status", "UNKNOWN")
        summary = item.get("summary", "")[:20].replace("\"", "'") + "..." if len(item.get("summary", "")) > 20 else item.get("summary", "")
        
        # 노드 ID 생성 (유니크하게)
        node_id = f"{step}_{i}"
        
        # 노드 정의 및 스타일링
        # 도형: 일반=[], 분기/옵션={{}}, 종료=(())
        shape_open = "["
        shape_close = "]"
        
        if step in ["option_pause", "ask_user"]:
             shape_open = "{{"
             shape_close = "}}"
        elif status == "FAILED":
             shape_open = "[/"
             shape_close = "/]"

        # 라벨에 이모지 및 요약 추가
        label = f"{step}\\n{summary}"
        
        mermaid_code.append(f"    {node_id}{shape_open}\"{label}\"{shape_close}")
        
        # 스타일링 클래스
        style_class = ""
        if status == "SUCCESS":
            style_class = "fill:#e6fffa,stroke:#00b894,stroke-width:2px"
        elif status == "FAILED":
            style_class = "fill:#fff5f5,stroke:#ff7675,stroke-width:2px"
        elif status == "PAUSED" or step == "option_pause":
            style_class = "fill:#fffce6,stroke:#fdcb6e,stroke-width:2px,stroke-dasharray: 5 5"
        elif status == "RUNNING":
             style_class = "fill:#e3f2fd,stroke:#74b9ff,stroke-width:4px"
        else:
             style_class = "fill:#f1f2f6,stroke:#ced6e0,stroke-width:1px"
             
        mermaid_code.append(f"    style {node_id} {style_class}")
        
        # 이전 노드와 연결
        mermaid_code.append(f"    {last_node_id} --> {node_id}")
        last_node_id = node_id
        
        # 에러 발생 시
        if item.get("error"):
             error_node_id = f"Error_{i}"
             mermaid_code.append(f"    {error_node_id}>\"❌ {item['error'][:20]}...\"]")
             mermaid_code.append(f"    style {error_node_id} fill:#ffadad,color:white")
             mermaid_code.append(f"    {node_id} -.-> {error_node_id}")

    # 렌더링
    st.markdown("##### 🧬 실행 흐름 시각화 (Live Graph)")
    diagram = "\n".join(mermaid_code)
    render_mermaid(diagram, height=300)
    
    # 원본 데이터는 접어서 보여줌
    with st.expander("📊 원본 데이터 보기"):
         st.json(step_history)


def render_progress_steps(current_step: str = None):
    """진행 상태 표시"""
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
    
    cols = st.columns(len(steps))
    for i, (step, key) in enumerate(zip(steps, step_keys)):
        with cols[i]:
            icon = step.split()[0]  # 이모지 추출
            if i < current_idx:
                # 완료된 단계
                st.markdown(f"<div style='text-align:center; color:#28a745; margin-bottom:5px;'>{icon}<br><small>✅</small></div>", unsafe_allow_html=True)
            elif i == current_idx:
                # 현재 단계
                st.markdown(f"<div style='text-align:center; color:#007bff; font-weight:bold; margin-bottom:5px;'>{icon}<br><small>▶️</small></div>", unsafe_allow_html=True)
            else:
                # 대기 단계
                st.markdown(f"<div style='text-align:center; color:#ddd; margin-bottom:5px;'>{icon}</div>", unsafe_allow_html=True)
    
    # 현재 단계 설명
    if current_step and current_step in step_descriptions:
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

    # Pydantic 모델 or Dict 처리
    options = getattr(current_state, "options", []) or current_state.get("options", [])
    if not options:
        return

    cols = st.columns(len(options))
    for i, opt in enumerate(options):
        # Pydantic model or dict
        title = getattr(opt, "title", opt.get("title", ""))
        description = getattr(opt, "description", opt.get("description", ""))
        
        with cols[i]:
            if st.button(f"{title}", key=f"opt_{i}", use_container_width=True, help=description):
                # 선택 처리 로직
                st.session_state.chat_history.append({
                    "role": "user", "content": f"'{title}' 선택", "type": "text"
                })
                
                # 입력 구성
                original_input = getattr(current_state, "user_input", current_state.get("user_input", ""))
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
