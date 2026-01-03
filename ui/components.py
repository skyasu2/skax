"""
UI Components Module

재사용 가능한 UI 컴포넌트들을 정의합니다.
"""

import streamlit as st
import streamlit.components.v1 as components
from ui.dynamic_form import render_pydantic_form  # [NEW]
  # [NEW] HTML 컴포넌트용



def render_scalable_mermaid(mermaid_code: str, height: int = 300):
    """
    [NEW] Mermaid 다이어그램을 적절한 크기로 렌더링 (HTML/JS 활용)
    기본 st.markdown보다 크기 제어가 용이하며, Fit-to-screen을 지원합니다.
    """
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
        </script>
        <style>
            .mermaid-container {{
                display: flex;
                justify_content: center;
                align-items: center;
                width: 100%;
                height: 100%;
                overflow: hidden; 
            }}
            /* SVG 크기 자동 조절 (Fit to Container) */
            svg {{
                max-width: 100% !important;
                max-height: {height}px !important;
                height: auto !important;
            }}
        </style>
    </head>
    <body>
        <div class="mermaid-container">
            <div class="mermaid">
                {mermaid_code}
            </div>
        </div>
    </body>
    </html>
    """
    # iframe 높이를 조절하여 스크롤 없이 보이게 함
    components.html(html_code, height=height+20, scrolling=False)


def render_mermaid(code: str, height: int = 600, scale: float = 1.0, auto_fit: bool = False):
    """
    Mermaid 다이어그램 렌더링 (통합 버전)

    Args:
        code: Mermaid 다이어그램 코드
        height: 렌더링 높이 (기본 600px)
        scale: 확대 배율 (auto_fit=False일 때 적용)
        auto_fit: True일 경우 컨테이너 너비에 맞춤 (반응형)
    """
    if auto_fit:
        # 반응형 (Fit to Container) 스타일
        css_style = f"""
        <style>
            .mermaid-container {{
                display: flex;
                justify_content: center;
                align-items: center;
                width: 100%;
                height: 100%;
                overflow: hidden;
            }}
            .mermaid {{
                width: 100%;
                text-align: center;
            }}
            /* SVG 크기 자동 조절 */
            svg {{
                max-width: 100% !important;
                height: auto !important;
                max-height: {height}px !important;
            }}
        </style>
        """
        scrolling = False
    else:
        # 고정 스케일 (스크롤 가능) 스타일
        css_style = f"""
        <style>
            .mermaid-container {{
                overflow: auto;
                padding: 10px;
            }}
            .mermaid {{
                transform: scale({scale});
                transform-origin: top left;
            }}
            .mermaid svg {{
                max-width: none !important;
            }}
        </style>
        """
        scrolling = True

    components.html(
        f"""
        {css_style}
        <div class="mermaid-container">
            <div class="mermaid">
                {code}
            </div>
        </div>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'neutral',
                themeVariables: {{
                    fontSize: '16px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif'
                }},
                flowchart: {{
                    nodeSpacing: 50,
                    rankSpacing: 50,
                    padding: 15,
                    htmlLabels: true,
                    curve: 'basis'
                }},
                gantt: {{
                    fontSize: 14,
                    barHeight: 25,
                    barGap: 6
                }}
            }});
        </script>
        """,
        height=height,
        scrolling=scrolling
    )


def render_markdown_with_mermaid(content: str):
    """
    [NEW] Mermaid 다이어그램을 포함한 마크다운 렌더링

    마크다운 콘텐츠에서 ```mermaid 블록을 추출하여
    별도의 render_mermaid()로 시각화하고, 나머지는 st.markdown()으로 렌더링합니다.

    Args:
        content: 마크다운 문자열 (Mermaid 블록 포함 가능)
    """
    import re

    # Mermaid 블록 패턴: ```mermaid ... ```
    mermaid_pattern = r'```mermaid\s*([\s\S]*?)```'

    # 모든 Mermaid 블록 찾기
    mermaid_blocks = re.findall(mermaid_pattern, content)

    if not mermaid_blocks:
        # Mermaid 블록이 없으면 그냥 마크다운 렌더링
        st.markdown(content)
        return

    # Mermaid 블록을 플레이스홀더로 대체
    parts = re.split(mermaid_pattern, content)

    # parts 구조: [text_before, mermaid_code_1, text_between, mermaid_code_2, ...]
    # 짝수 인덱스: 일반 텍스트, 홀수 인덱스: Mermaid 코드
    for i, part in enumerate(parts):
        if not part.strip():
            continue

        if i % 2 == 0:
            # 일반 마크다운 텍스트
            st.markdown(part)
        else:
            # Mermaid 코드 블록 - 시각적 렌더링 (반응형 fit)
            st.markdown("---")
            st.caption("📊 Mermaid 다이어그램")
            # auto_fit=True로 설정하여 화면에 맞게 렌더링
            render_mermaid(part.strip(), height=500, auto_fit=True)
            st.markdown("---")


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


def render_specialist_agents_status(specialist_analysis: dict = None, is_running: bool = False):
    """
    전문 에이전트 분석 상태 표시
    
    Multi-Agent Supervisor의 4개 전문 에이전트 진행/완료 상태를 시각화합니다.
    
    Args:
        specialist_analysis: 전문 에이전트 분석 결과 (dict)
        is_running: 현재 분석 중인지 여부
    """
    agents = [
        {"key": "market_analysis", "name": "시장 분석", "icon": "📊", "desc": "TAM/SAM/SOM, 경쟁사"},
        {"key": "business_model", "name": "비즈니스 모델", "icon": "💰", "desc": "수익 모델, 가격 전략"},
        {"key": "tech_architecture", "name": "기술 아키텍처", "icon": "🏗️", "desc": "스택, 인프라, 로드맵"},
        {"key": "content_strategy", "name": "콘텐츠 전략", "icon": "📣", "desc": "브랜딩, 유입, 마케팅"},
        {"key": "financial_plan", "name": "재무 계획", "icon": "📈", "desc": "투자비, BEP, 손익"},
        {"key": "risk_analysis", "name": "리스크", "icon": "⚠️", "desc": "8가지 리스크 분석"},
    ]
    
    if is_running:
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px;
            border-radius: 12px;
            margin-bottom: 16px;
        ">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.5rem;">🤖</span>
                <div>
                    <strong>전문 에이전트 분석 중...</strong>
                    <p style="margin: 4px 0 0 0; font-size: 0.85rem; opacity: 0.9;">
                        4개의 전문 AI 에이전트가 병렬로 분석을 수행하고 있습니다
                    </p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 진행 중 애니메이션
        # 진행 중 애니메이션 (3열 그리드)
        cols = st.columns(3)
        for i, agent in enumerate(agents):
            col_idx = i % 3
            if col_idx == 0 and i > 0:
                 cols += st.columns(3) # 새 줄 추가 (이 방식은 streamlit에서 안됨. 미리 6개 깔거나 나눠야 함)
            
            # 간단히 3열 2행으로 처리
            col_to_use = cols[col_idx] if i < 3 else st.columns(3)[col_idx] if i == 3 else cols[col_idx] # 복잡함.
            
        # 3열 Grid Helper
        grid_cols = st.columns(3)
        grid_cols_2 = st.columns(3)
        
        for i, agent in enumerate(agents):
            target_col = grid_cols[i] if i < 3 else grid_cols_2[i-3]
            with target_col:
                st.markdown(f"""
                <div style="
                    text-align: center;
                    padding: 12px 8px;
                    background: #f8f9fa;
                    border-radius: 8px;
                    border: 2px dashed #667eea;
                ">
                    <div style="font-size: 1.5rem;">{agent['icon']}</div>
                    <div style="font-size: 0.8rem; font-weight: bold; margin: 4px 0;">{agent['name']}</div>
                    <div style="font-size: 0.7rem; color: #666;">⏳ 분석 중...</div>
                </div>
                """, unsafe_allow_html=True)
        return
    
    if not specialist_analysis:
        return
    
    # 분석 완료 상태 표시
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        color: white;
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 16px;
    ">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.5rem;">✅</span>
            <div>
                <strong>전문 에이전트 분석 완료!</strong>
                <p style="margin: 4px 0 0 0; font-size: 0.85rem; opacity: 0.9;">
                    아래 분석 결과가 기획서 작성에 자동 반영됩니다
                </p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 완료된 에이전트 결과 표시
    # 완료된 에이전트 결과 표시 (3열 그리드)
    grid_cols = st.columns(3)
    grid_cols_2 = st.columns(3)
    
    for i, agent in enumerate(agents):
        target_col = grid_cols[i] if i < 3 else grid_cols_2[i-3]
        
        result = specialist_analysis.get(agent["key"])
        is_done = result is not None
        
        with target_col:
            if is_done:
                st.markdown(f"""
                <div style="
                    text-align: center;
                    padding: 12px 8px;
                    background: #e8f5e9;
                    border-radius: 8px;
                    border: 2px solid #4caf50;
                ">
                    <div style="font-size: 1.5rem;">{agent['icon']}</div>
                    <div style="font-size: 0.8rem; font-weight: bold; margin: 4px 0; color: #2e7d32;">{agent['name']}</div>
                    <div style="font-size: 0.7rem; color: #4caf50;">✓ 완료</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="
                    text-align: center;
                    padding: 12px 8px;
                    background: #ffebee;
                    border-radius: 8px;
                    border: 2px solid #ef5350;
                ">
                    <div style="font-size: 1.5rem;">{agent['icon']}</div>
                    <div style="font-size: 0.8rem; font-weight: bold; margin: 4px 0; color: #c62828;">{agent['name']}</div>
                    <div style="font-size: 0.7rem; color: #ef5350;">✗ 미완료</div>
                </div>
                """, unsafe_allow_html=True)
    
    # 상세 결과 Expander
    with st.expander("🔍 전문 에이전트 분석 상세 결과", expanded=False):
        # [NEW] 실행 통계 탭 추가: _execution_stats가 있으면 통계 탭을 가장 앞에 표시
        stats = specialist_analysis.get("_execution_stats")
        
        tab_titles = []
        if stats:
            tab_titles.append("📊 시스템 통계")
            
        tab_titles.extend([f"{a['icon']} {a['name']}" for a in agents])
        tabs = st.tabs(tab_titles)
        
        current_tab_idx = 0
        
        # 1. 시스템 통계 렌더링
        if stats:
            with tabs[current_tab_idx]:
                st.markdown("#### ⚡ Multi-Agent Execution Stats")
                
                # 요약 메트릭
                m1, m2, m3, m4 = st.columns(4)
                
                # Duration 계산
                start = stats.get("started_at")
                end = stats.get("completed_at")
                duration = "N/A"
                if start and end:
                    from datetime import datetime
                    try:
                        s = datetime.fromisoformat(start)
                        e = datetime.fromisoformat(end)
                        duration = f"{(e-s).total_seconds():.2f}s"
                    except:
                        pass
                
                # Fallback duration if calculation fails
                if duration == "N/A" and "agent_stats" in stats:
                     total_ms = sum(a.get("execution_time_ms", 0) for a in stats["agent_stats"].values())
                     # Simply sum might be wrong for parallel, but good enough approximation if start/end missing
                     pass 

                with m1:
                    st.metric("총 소요 시간", duration)
                with m2:
                    st.metric("성공/실패", f"{stats.get('successful_agents', 0)} / {stats.get('failed_agents', 0)}")
                with m3:
                    st.metric("재시도 횟수", f"{stats.get('retried_agents', 0)}")
                with m4:
                    st.metric("Fallback 사용", f"{stats.get('fallback_used_count', 0)}")
                
                st.divider()
                
                # 에이전트별 상세 테이블
                agent_stats = stats.get("agent_stats", {})
                if agent_stats:
                    st.markdown("##### 🕵️ 에이전트별 성능")
                    stat_data = []
                    for aid, a_stat in agent_stats.items():
                        stat_data.append({
                             "Agent": aid,
                             "Status": "✅ Success" if a_stat.get("success") else "❌ Failed",
                             "Time": f"{a_stat.get('execution_time_ms', 0):.0f}ms",
                             "Retries": a_stat.get("retry_count", 0),
                             "Fallback": "⚡ Yes" if a_stat.get("fallback_used") else "-",
                             "Error": a_stat.get("error_category", "-")
                        })
                    st.dataframe(stat_data, use_container_width=True)

            current_tab_idx += 1
        
        # 2. 각 에이전트 결과 렌더링
        for i, agent in enumerate(agents):
            with tabs[current_tab_idx + i]:
                result = specialist_analysis.get(agent["key"])
                if result:
                    # 마크다운 렌더링 지원 (fallback 필드 등 확인)
                    if isinstance(result, dict) and "_fallback_reason" in result:
                        st.warning(f"⚠️ Fallback 사용됨: {result['_fallback_reason']}")
                    
                    st.json(result)
                else:
                    st.info("분석 결과 없음")


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
        opt_id = safe_get(opt, "id", "")

        with cols[i]:
            if st.button(f"{title}", key=f"opt_{i}", use_container_width=True, help=description):
                # [FIX] "수정" 옵션 선택 시 초기 화면으로 리셋
                # 사용자가 처음부터 다시 입력하고 파일 업로드할 수 있게 함
                is_retry_option = (
                    opt_id == "retry" or
                    "수정" in title or
                    "아니요" in title or
                    "취소" in title
                )

                if is_retry_option:
                    # 세션 상태 초기화 (처음 화면으로)
                    st.session_state.chat_history = []
                    st.session_state.current_state = None
                    st.session_state.generated_plan = None
                    st.session_state.uploaded_content = None
                    st.session_state.pending_input = None
                    st.session_state.prefill_prompt = None
                    st.session_state.input_key += 1
                    import uuid
                    st.session_state.thread_id = str(uuid.uuid4())
                    st.toast("🔄 처음 화면으로 돌아갑니다. 새로운 아이디어를 입력해주세요!")
                    st.rerun()
                    return

                # 일반 옵션 선택 처리 로직
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
