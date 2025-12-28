"""
UI Dialogs Module

모달/다이얼로그 컴포넌트들을 정의합니다.
"""

import os
import streamlit as st
from datetime import datetime


@st.dialog("📄 생성된 기획서", width="large")
def show_plan_dialog():
    """기획서 상세 보기 모달 (버전 관리 포함)"""
    from tools.file_utils import save_plan
    
    if not st.session_state.generated_plan:
        st.warning("생성된 기획서가 없습니다.")
        return

    # 버전 선택 UI
    history = st.session_state.get("plan_history", [])
    selected_plan = st.session_state.generated_plan
    is_latest = True
    
    if len(history) > 1:
        col_ver, col_empty = st.columns([1, 2])
        with col_ver:
            options = [f"v{h['version']} ({h['timestamp']})" for h in reversed(history)]
            selected_option = st.selectbox("🕒 버전 선택", options, index=0)
            
            version_str = selected_option.split("v")[1].split(" ")[0]
            version_idx = int(version_str)
            
            latest_version = history[-1]['version']
            is_latest = (version_idx == latest_version)
            
            for h in history:
                if h['version'] == version_idx:
                    selected_plan = h['content']
                    break
    
    if not is_latest:
        st.warning(f"⚠️ **v{version_idx} (과거 버전)**을 보고 있습니다. 현재 편집하거나 다운로드할 수 없습니다.")
    else:
        if st.session_state.current_state:
            state = st.session_state.current_state
            refined = state.get("refined", False)
            
            final_doc = selected_plan
            section_count = 0
            if final_doc:
                section_count = final_doc.count("\n## ")
                if section_count == 0 and "## " in final_doc:
                    section_count = final_doc.count("## ")
            
            if section_count == 0:
                draft = state.get("draft", {})
                section_count = len(draft.get("sections", []))

            analysis = state.get("analysis")
            key_features = []

            if analysis:
                from graph.state import safe_get
                key_features = safe_get(analysis, "key_features", [])
            
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
                st.metric("섹션 (목차 개수)", f"{section_count}개", 
                    help="기획서의 큰 목차(Chapter) 개수입니다.")
            with col3:
                st.metric("핵심 기능 (주요 아이디어)", f"{feature_count}개", 
                    help="AI가 분석한 이 서비스의 주요 기능입니다.")

    # 탭
    tab1, tab2 = st.tabs(["📖 미리보기", "📝 마크다운"])
    with tab1:
        st.markdown(selected_plan)
    with tab2:
        st.code(selected_plan, language="markdown")

    # 버튼
    if is_latest:
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.download_button("📥 다운로드", data=selected_plan, file_name="기획서.md",
                mime="text/markdown", use_container_width=True)
        with col2:
            if st.button("💾 서버에 저장", use_container_width=True):
                saved_path = save_plan(selected_plan)
                st.success(f"서버에 저장됨: {os.path.basename(saved_path)}")
        with col3:
            if st.button("✖️ 닫기", use_container_width=True):
                st.rerun()


@st.dialog("🔍 AI 분석 데이터 (설계도)", width="large")
def show_analysis_dialog():
    """분석 결과 상세 보기 모달"""
    if not st.session_state.current_state:
        st.warning("분석 결과가 없습니다.")
        return

    state = st.session_state.current_state
    has_content = False

    def safe_dump(data):
        if hasattr(data, "model_dump"):
            return data.model_dump()
        if hasattr(data, "dict"):
            return data.dict()
        return data

    try:
        if state.get("analysis"):
            st.subheader("🔍 입력 분석")
            st.json(safe_dump(state["analysis"]))
            has_content = True

        if state.get("structure"):
            st.subheader("📐 구조 설계")
            st.json(safe_dump(state["structure"]))
            has_content = True

        if state.get("review"):
            st.subheader("📝 검토 결과")
            st.json(safe_dump(state["review"]))
            has_content = True
            
        if not has_content:
            st.info("⚠️ 상세 분석 데이터가 없습니다. (일반 응답이거나 데이터가 유실되었습니다.)")
            with st.expander("디버깅용 전체 상태 확인 (Raw)", expanded=False):
                st.json(safe_dump(state))
                
    except Exception as e:
        st.error(f"데이터 렌더링 중 오류가 발생했습니다: {str(e)}")
        with st.expander("상세 에러", expanded=False):
            st.write(e)


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
    tab_test, tab_graph, tab_history, tab_schema = st.tabs(
        ["🧪 Agent Unit Test", "📊 Workflow Graph", "🕰️ State History", "📐 Schema Viewer"]
    )
    
    # =========================================================================
    # Tab 1: Agent Unit Test
    # =========================================================================
    with tab_test:
        st.markdown("### Agent 단위 테스트")
        st.info("각 Agent를 개별적으로 실행하여 로직을 검증합니다.")
        st.markdown("---")
        
        agent_type = st.selectbox("Agent 테스트", ["None", "Analyzer", "Structurer", "Writer", "Reviewer"])
        
        if agent_type != "None":
            st.write(f"**Target:** `{agent_type}` Agent")
            
            test_input = "점심 메뉴 추천 앱"
            if agent_type == "Writer":
                test_input = st.text_area("입력 (가상 시나리오)", value="점심 메뉴 추천 서비스 기획해줘", height=70)
            
            if st.button("🚀 테스트 실행", key="test_run_btn", use_container_width=True):
                with st.spinner(f"{agent_type} Agent 실행 중..."):
                    try:
                        from graph.state import create_initial_state, update_state, safe_get

                        # TypedDict 기반 상태 생성
                        mock_state = create_initial_state(test_input)
                        result_state = None

                        def safe_dump(data):
                            """Pydantic 또는 dict 데이터를 안전하게 변환"""
                            if data is None:
                                return {}
                            if hasattr(data, "model_dump"):
                                return data.model_dump()
                            if hasattr(data, "dict"):
                                return data.dict()
                            return data

                        if agent_type == "Analyzer":
                            from agents.analyzer import run
                            result_state = run(mock_state)
                            st.subheader("결과 (AnalysisResult)")
                            st.json(safe_dump(result_state.get("analysis")))

                        elif agent_type == "Structurer":
                            from agents.structurer import run
                            from utils.schemas import AnalysisResult
                            analysis_data = AnalysisResult(
                                topic="점심 추천 앱", purpose="직장인 점심 고민 해결",
                                target_users="직장인", key_features=["랜덤 추천", "주변 식당 지도"],
                                need_more_info=False
                            )
                            mock_state = update_state(mock_state, analysis=analysis_data.model_dump())
                            result_state = run(mock_state)
                            st.subheader("결과 (StructureResult)")
                            st.json(safe_dump(result_state.get("structure")))

                        elif agent_type == "Writer":
                            from agents.writer import run
                            from utils.schemas import StructureResult, SectionStructure
                            structure_data = StructureResult(
                                title="점심 추천 앱 기획서",
                                sections=[
                                    SectionStructure(id=1, name="개요", description="앱 소개", key_points=["목적 설명"]),
                                    SectionStructure(id=2, name="기능", description="주요 기능", key_points=["기능 나열"])
                                ]
                            )
                            mock_state = update_state(mock_state, structure=structure_data.model_dump())
                            result_state = run(mock_state)
                            st.subheader("결과 (DraftResult)")
                            st.json(safe_dump(result_state.get("draft")))

                        elif agent_type == "Reviewer":
                            from agents.reviewer import run
                            from utils.schemas import DraftResult, SectionContent
                            draft_data = DraftResult(
                                sections=[
                                    SectionContent(id=1, name="개요", content="이 앱은 점심을 추천해줍니다."),
                                    SectionContent(id=2, name="기능", content="랜덤 추천 기능이 있습니다.")
                                ]
                            )
                            mock_state = update_state(mock_state, draft=draft_data.model_dump())
                            result_state = run(mock_state)
                            st.subheader("결과 (JudgeResult)")
                            st.json(safe_dump(result_state.get("review")))

                        if result_state:
                            st.success("✅ 테스트 성공")
                        
                    except Exception as e:
                        st.error(f"❌ 테스트 실패: {str(e)}")
                        st.exception(e)
    
    # =========================================================================
    # Tab 2: Workflow Graph
    # =========================================================================
    with tab_graph:
        st.markdown("---")
        st.subheader("📊 Workflow Visualization")
        
        current_step = None
        if st.session_state.current_state:
            current_step = st.session_state.current_state.get("current_step", None)
        
        try:
            from graph.workflow import app as workflow_app
            mermaid_code = workflow_app.get_graph().draw_mermaid()
            
            if current_step and current_step in mermaid_code:
                highlight_style = f"\n\tstyle {current_step} fill:#90EE90,stroke:#228B22,stroke-width:3px"
                if "end" in mermaid_code.lower():
                    mermaid_code = mermaid_code.rstrip() + highlight_style
                else:
                    mermaid_code += highlight_style
                
                st.success(f"🟢 현재 단계: **{current_step.upper()}** (녹색으로 강조)")
            else:
                st.info("💡 기획서를 생성하면 현재 실행 단계가 강조됩니다.")
            
            st.markdown(f"```mermaid\n{mermaid_code}\n```")
            
        except Exception as e:
            st.warning(f"Graph Visualization unavailable: {e}")

    # =========================================================================
    # Tab 3: State History (Time-Travel)
    # =========================================================================
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
                    st.session_state.history_cache = history
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
                        if i > 0:
                            if st.button(f"⏪ 롤백", key=f"rollback_{i}", use_container_width=True):
                                try:
                                    from graph.workflow import app as workflow_app
                                    workflow_app.update_state(h.config, h.values, as_node=h.next[0] if h.next else None)
                                    st.session_state.current_state = h.values
                                    if h.values.get("final_output"):
                                        st.session_state.generated_plan = h.values.get("final_output")
                                    st.success(f"✅ #{i+1} 시점으로 롤백되었습니다!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"롤백 실패: {str(e)}")
                        else:
                            st.caption("(현재)")
                    
                    with st.container():
                        st.json(h.values)
            
            # State Diff 비교 섹션
            st.markdown("---")
            st.subheader("🔄 State Diff (스냅샷 비교)")
            
            if len(history) >= 2:
                col_left, col_right = st.columns(2)
                snapshot_options = [f"#{i+1} | {h.next[0] if h.next else 'END'}" for i, h in enumerate(history)]
                
                with col_left:
                    left_idx = st.selectbox("비교 기준 (Before)", options=range(len(history)), 
                                           format_func=lambda x: snapshot_options[x], key="diff_left")
                with col_right:
                    right_idx = st.selectbox("비교 대상 (After)", options=range(len(history)), 
                                            format_func=lambda x: snapshot_options[x], key="diff_right",
                                            index=min(1, len(history)-1))
                
                if st.button("🔍 차이점 비교", key="btn_compare", use_container_width=True):
                    left_values = history[left_idx].values
                    right_values = history[right_idx].values
                    
                    all_keys = set(left_values.keys()) | set(right_values.keys())
                    changed_keys, added_keys, removed_keys = [], [], []
                    
                    for key in all_keys:
                        if key not in left_values:
                            added_keys.append(key)
                        elif key not in right_values:
                            removed_keys.append(key)
                        elif left_values[key] != right_values[key]:
                            changed_keys.append(key)
                    
                    if not (changed_keys or added_keys or removed_keys):
                        st.info("✅ 두 스냅샷이 동일합니다.")
                    else:
                        st.markdown(f"**변경: {len(changed_keys)}개** | **추가: {len(added_keys)}개** | **제거: {len(removed_keys)}개**")
                        
                        if changed_keys:
                            st.markdown("##### 🔄 변경된 필드")
                            for key in changed_keys:
                                with st.expander(f"`{key}`", expanded=False):
                                    col_before, col_after = st.columns(2)
                                    with col_before:
                                        st.caption("Before")
                                        st.code(str(left_values.get(key, "N/A"))[:500], language="json")
                                    with col_after:
                                        st.caption("After")
                                        st.code(str(right_values.get(key, "N/A"))[:500], language="json")
                        
                        if added_keys:
                            st.markdown("##### ➕ 추가된 필드")
                            for key in added_keys:
                                st.markdown(f"- `{key}`")
                        
                        if removed_keys:
                            st.markdown("##### ➖ 제거된 필드")
                            for key in removed_keys:
                                st.markdown(f"- `{key}`")
            else:
                st.info("비교하려면 최소 2개의 스냅샷이 필요합니다.")

    # =========================================================================
    # Tab 4: Schema Viewer
    # =========================================================================
    with tab_schema:
        st.subheader("📐 Pydantic Schema Viewer")
        st.info("State 및 Output 스키마를 JSON Schema 형태로 확인할 수 있습니다.")
        
        schema_type = st.selectbox(
            "스키마 선택",
            ["PlanCraftState", "AnalysisResult", "StructureResult", "DraftResult", "JudgeResult"],
            key="schema_select"
        )
        
        try:
            if schema_type == "PlanCraftState":
                # TypedDict는 model_json_schema()가 없으므로 __annotations__ 사용
                from graph.state import PlanCraftState
                from typing import get_type_hints
                try:
                    annotations = get_type_hints(PlanCraftState)
                    schema = {
                        "title": "PlanCraftState",
                        "type": "object",
                        "description": "PlanCraft Agent 전체 내부 상태 (TypedDict 기반)",
                        "properties": {
                            key: {"type": str(value)}
                            for key, value in annotations.items()
                        }
                    }
                except Exception:
                    schema = {"title": "PlanCraftState", "note": "TypedDict - use get_type_hints() for schema"}
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
