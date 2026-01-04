"""
UI Dialog: Dev Tools
"""
import streamlit as st
import os
import sys
from datetime import datetime

@st.dialog("🛠️ Dev Tools", width="large")
def render_dev_tools():
    """개발자 도구 (모달)"""
    tab_test, tab_all_tests, tab_graph, tab_history, tab_schema = st.tabs(
        ["🧪 Agent Unit Test", "✅ Run ALL Tests", "📊 Workflow Graph", "🕰️ State History", "📐 Schema Viewer"]
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
    # Tab 1.5: Run ALL Tests
    # =========================================================================
    with tab_all_tests:
        st.markdown("### 🚀 시스템 전체 테스트 (System Integration Test)")
        st.info("터미널 없이 전체 테스트를 실행하고, 리포트를 즉시 확인합니다.")
        
        reports_dir = "reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        # 리포트 목록 가져오기 (최신순)
        def get_report_list():
            if not os.path.exists(reports_dir):
                return []
            files = [f for f in os.listdir(reports_dir) if f.startswith("test_report_") and f.endswith(".html")]
            files.sort(reverse=True)  # 최신순 정렬
            return files[:10]  # 최대 10개
        
        # 오래된 리포트 정리 (10개 초과 시 삭제)
        def cleanup_old_reports():
            files = [f for f in os.listdir(reports_dir) if f.startswith("test_report_") and f.endswith(".html")]
            files.sort(reverse=True)
            for old_file in files[10:]:  # 10개 초과 삭제
                try:
                    os.remove(os.path.join(reports_dir, old_file))
                except:
                    pass
        
        col_run, col_status = st.columns([1, 2])
        with col_run:
            if st.button("▶️ 전체 테스트 실행", type="primary", use_container_width=True):
                import subprocess
                import sys
                
                # 타임스탬프 기반 리포트 파일명
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_filename = f"test_report_{timestamp}.html"
                report_path = os.path.join(reports_dir, report_filename)
                
                # pytest 명령어
                pytest_cmd = [
                    sys.executable, "-m", "pytest",
                    "tests/",
                    f"--html={report_path}",
                    "--self-contained-html",
                    "-v", "--tb=short"
                ]
                
                # [백그라운드 실행] Popen 사용
                try:
                    process = subprocess.Popen(
                        pytest_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        cwd=os.getcwd()
                    )
                    st.session_state["test_running"] = True
                    st.session_state["test_pid"] = process.pid
                    st.session_state["latest_report"] = report_filename
                    st.success(f"🚀 테스트가 백그라운드에서 시작되었습니다!")
                    st.caption(f"PID: {process.pid} | 리포트: {report_filename}")
                    st.info("완료 후 페이지를 새로고침하면 결과가 표시됩니다.")
                    
                    # 오래된 리포트 정리
                    cleanup_old_reports()
                except Exception as e:
                    st.error(f"테스트 시작 실패: {str(e)}")

        with col_status:
            report_list = get_report_list()
            if report_list:
                st.success(f"✅ 저장된 리포트: {len(report_list)}개")
            elif st.session_state.get("test_running"):
                st.warning("⏳ 테스트 실행 중... (완료되면 새로고침)")
            else:
                st.caption("리포트 없음")

        st.divider()

        # 리포트 목록 및 뷰어
        report_list = get_report_list()
        if report_list:
            st.session_state["test_running"] = False
            
            st.markdown("#### 📋 Test Report History (최근 10개)")
            
            col_sel, col_btn = st.columns([3, 1])
            with col_sel:
                selected_report = st.selectbox(
                    "리포트 선택",
                    report_list,
                    format_func=lambda x: f"📄 {x.replace('test_report_', '').replace('.html', '').replace('_', ' ')}"
                )
            
            if selected_report:
                report_path = os.path.join(reports_dir, selected_report)
                abs_path = os.path.abspath(report_path)
                
                with col_btn:
                    st.write("") # Spacer
                with col_btn:
                    st.write("") # Spacer
                    with open(report_path, "rb") as file:
                        st.download_button(
                            label="📥 리포트 다운로드",
                            data=file,
                            file_name=selected_report,
                            mime="text/html",
                            type="primary",
                            use_container_width=True
                        )

                # 간단한 미리보기 (선택 사항)
                with st.expander("🔽 여기서 미리보기 (Embedded View)"):
                    try:
                        with open(report_path, "r", encoding="utf-8") as f:
                            html_content = f.read()
                        import streamlit.components.v1 as components
                        components.html(html_content, height=800, scrolling=True)
                    except Exception as e:
                        st.error(f"리포트 로드 실패: {e}")
        else:
            st.info("테스트를 실행하면 여기에 리포트가 표시됩니다.")

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
