"""
워크플로우 실행 모듈

app.py의 pending_input 처리 로직을 분리하여 모듈화합니다.
FastAPI 백엔드와의 통신, 폴링, 결과 처리를 담당합니다.
"""

import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

import httpx
import streamlit as st


from utils.config import Config

# API Base URL - Removed safely
# API_BASE_URL = Config.API_BASE_URL


def check_api_health(timeout: float = 2.0) -> Tuple[bool, str]:
    """
    API 서버 상태를 확인합니다.

    Args:
        timeout: 타임아웃 (초)

    Returns:
        Tuple[bool, str]: (정상 여부, 에러 메시지)
    """
    try:
        # /api/v1 제거하고 /health 엔드포인트 호출
        base_url = Config.API_BASE_URL.replace("/api/v1", "")
        resp = httpx.get(f"{base_url}/health", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("service") == "plancraft-api":
                return True, ""
            return False, "알 수 없는 서비스가 응답했습니다"
        return False, f"서버 응답 오류 (status={resp.status_code})"
    except httpx.ConnectError:
        return False, "API 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요."
    except httpx.TimeoutException:
        return False, "API 서버 응답 시간 초과"
    except Exception as e:
        return False, f"API 서버 확인 실패: {e}"


# 단계별 진행률 매핑
STEP_PROGRESS = {
    "router": 5,                     # [NEW] Smart Router
    "retrieve": 10, "context": 10,
    "analyze": 25,
    "structure": 40,
    "write": 60,
    "review": 75,
    "refine": 85,
    "format": 95,
}

STEP_LABELS = {
    "router": ("🚦", "입력 분류"),   # [NEW] Smart Router
    "retrieve": ("📚", "컨텍스트 수집"),
    "context": ("📚", "컨텍스트 수집"),
    "analyze": ("🔍", "요구사항 분석"),
    "structure": ("🏗️", "구조 설계"),
    "write": ("✍️", "콘텐츠 작성"),
    "review": ("🔎", "품질 검토"),
    "refine": ("✨", "내용 개선"),
    "format": ("📋", "최종 포맷팅"),
}


def parse_resume_command(pending_text: str) -> Optional[Dict[str, Any]]:
    """
    사용자 입력에서 Resume 명령을 파싱합니다.

    Args:
        pending_text: 사용자 입력 텍스트

    Returns:
        resume_cmd: Resume 명령 딕셔너리 또는 None
    """
    resume_cmd = None

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

    return resume_cmd


def execute_workflow_api(
    pending_text: str,
    resume_cmd: Optional[Dict],
    thread_id: str,
    generation_preset: str,
    file_content: Optional[str],
    refine_count: int,
    previous_plan: Optional[str]
) -> httpx.Response:
    """
    워크플로우 API를 호출합니다.

    Args:
        pending_text: 사용자 입력
        resume_cmd: Resume 명령 (있으면 재개, 없으면 신규 실행)
        thread_id: 스레드 ID
        generation_preset: 생성 프리셋
        file_content: 업로드된 파일 내용
        refine_count: 개선 횟수
        previous_plan: 이전 기획서

    Returns:
        httpx.Response: API 응답
    """
    if resume_cmd:
        # Resume 요청 (HITL 재개)
        response = httpx.post(
            f"{Config.API_BASE_URL}/workflow/resume",
            json={
                "thread_id": thread_id,
                "resume_data": resume_cmd["resume"],
                "generation_preset": generation_preset,
            },
            timeout=30.0
        )
    else:
        # 신규 실행
        response = httpx.post(
            f"{Config.API_BASE_URL}/workflow/run",
            json={
                "user_input": pending_text,
                "file_content": file_content,
                "thread_id": thread_id,
                "generation_preset": generation_preset,
                "refine_count": refine_count,
                "previous_plan": previous_plan
            },
            timeout=30.0
        )

    if response.is_error:
        print(f"[API ERROR] Status: {response.status_code}, Body: {response.text}")
        try:
            error_detail = response.json()
            if "detail" in error_detail:
                from utils.file_logger import logger
                logger.error(f"Validation Detail: {error_detail['detail']}")
                st.error(f"요청 데이터 오류 (Validation Error): {error_detail['detail']}")
        except Exception:
            pass

    response.raise_for_status()
    return response


def poll_workflow_status(
    thread_id: str,
    status_widget,
    progress_bar,
    current_step_display,
    on_log_callback=None  # [NEW] Callback for real-time logging
) -> Tuple[Dict[str, Any], list]:
    """
    워크플로우 상태를 폴링하여 완료될 때까지 대기합니다.

    Args:
        thread_id: 스레드 ID
        status_widget: Streamlit status 위젯
        progress_bar: 진행률 바
        current_step_display: 현재 단계 표시 위젯
        on_log_callback: 로그 발생 시 호출할 콜백 함수

    Returns:
        Tuple[final_result, execution_log]: 최종 결과와 실행 로그
    """
    MAX_POLL_DURATION = 600  # 최대 10분
    MAX_CONSECUTIVE_ERRORS = 10
    POLL_INTERVAL = 1.0
    INITIAL_WAIT_TIME = 5.0

    last_step_count = 0
    final_result = None
    start_time = time.time()
    execution_log = []
    consecutive_errors = 0
    current_progress = 0

    while True:
        elapsed = int(time.time() - start_time)

        # 타임아웃 체크
        if elapsed > MAX_POLL_DURATION:
            raise TimeoutError(f"작업 시간이 초과되었습니다 ({MAX_POLL_DURATION}초)")

        # 상태 조회
        try:
            status_res = httpx.get(
                f"{Config.API_BASE_URL}/workflow/status/{thread_id}",
                timeout=10.0
            )

            if status_res.status_code == 404:
                if elapsed < INITIAL_WAIT_TIME:
                    current_step_display.markdown("⏳ **초기화 중...** 워크플로우를 준비하고 있습니다")
                    time.sleep(POLL_INTERVAL)
                    continue
                raise ValueError("워크플로우를 찾을 수 없습니다")
            elif status_res.status_code >= 500:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    raise RuntimeError(f"서버 오류가 계속 발생합니다 ({consecutive_errors}회)")
                time.sleep(POLL_INTERVAL * 2)
                continue
            elif status_res.status_code != 200:
                consecutive_errors += 1
                time.sleep(POLL_INTERVAL)
                continue

            consecutive_errors = 0

        except httpx.RequestError as e:
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                raise ConnectionError(f"네트워크 연결 오류: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        status_data = status_res.json()
        current_status = status_data.get("status", "running")
        step_history = status_data.get("step_history", [])
        current_step = status_data.get("current_step", "")

        # 현재 단계 업데이트
        for step_key, progress in STEP_PROGRESS.items():
            if current_step and step_key in current_step.lower():
                if progress > current_progress:
                    current_progress = progress
                    progress_bar.progress(min(current_progress / 100, 0.95))
                    icon, label = STEP_LABELS.get(step_key, ("▶️", current_step))
                    status_widget.update(label=f"{icon} {label} ({elapsed}초)", state="running")
                    current_step_display.markdown(f"🟢 **진행 중:** {label} 단계")
                break

        # 로그 수집 & 콜백 실행 (Step History + Execution Log)
        # 1. Step History 처리
        if len(step_history) > last_step_count:
            new_steps = step_history[last_step_count:]
            last_step_count = len(step_history)
            
            for step in new_steps:
                step_name = step.get("step", "Unknown")
                summary = step.get("summary", "")
                exec_time = step.get("execution_time", "")
                
                icon = "✔"
                for key, (ic, _) in STEP_LABELS.items():
                    if key in step_name.lower():
                        icon = ic
                        break
                        
                log_entry = {
                    "step": step_name,
                    "summary": f"[{icon}] {step_name} 완료: {summary} ({exec_time})",
                    "timestamp": time.time()
                }
                if not on_log_callback:
                     status_widget.write(log_entry["summary"])
                
                execution_log.append(log_entry)
                
                if on_log_callback:
                    # [FIX] 문자열 대신 Dict 객체 전체 전달 (TypeError 해결)
                    on_log_callback({
                        "step": step_name,
                        "icon": icon,
                        "summary": summary
                    })

        # 2. Execution Log (Real-time Events) 처리
        server_exec_log = status_data.get("execution_log", [])
        current_exec_log_count = getattr(poll_workflow_status, "last_exec_log_count", 0)
        
        if len(server_exec_log) > current_exec_log_count:
            new_events = server_exec_log[current_exec_log_count:]
            poll_workflow_status.last_exec_log_count = len(server_exec_log)
            
            for event in new_events:
                msg = event.get("message", "")
                if msg:
                     if not on_log_callback:
                         status_widget.write(f"  ↳ {msg}")
                     
                     if on_log_callback:
                         # [FIX] Real-time event도 Dict 형태로 전달
                         on_log_callback({
                             "step": "Running",
                             "icon": "⚡",
                             "summary": msg
                         })




        # 종료 조건 확인
        if current_status in ["completed", "interrupted", "failed"]:
            final_result = status_data.get("result")
            if not final_result:
                time.sleep(0.5)
                retry_res = httpx.get(
                    f"{Config.API_BASE_URL}/workflow/status/{thread_id}",
                    timeout=5.0
                )
                if retry_res.status_code == 200:
                    final_result = retry_res.json().get("result")
            if not final_result:
                raise Exception("작업이 완료되었으나 결과 데이터를 받아올 수 없습니다.")
            break

        time.sleep(POLL_INTERVAL)

    return final_result, execution_log


def handle_workflow_result(final_result: Dict[str, Any], status_data: Dict = None):
    """
    워크플로우 결과를 처리하여 세션 상태를 업데이트합니다.

    Args:
        final_result: 워크플로우 실행 결과
        status_data: 상태 데이터 (토큰 사용량 등)
    """
    # API 응답 필드 매핑
    if final_result.get("interrupt"):
        final_result["__interrupt__"] = final_result["interrupt"]

    # 결과 State 저장
    st.session_state.current_state = final_result
    current_refine_count = st.session_state.get("next_refine_count", 0)
    if current_refine_count > 0:
        final_result["refine_count"] = current_refine_count
        st.session_state.next_refine_count = 0

    # 결과 분석
    analysis_res = final_result.get("analysis")
    generated_plan = final_result.get("final_output", "")
    interrupt_data = final_result.get("__interrupt__")

    # 상태값 초기화
    options = final_result.get("options", [])
    option_question = final_result.get("option_question", "다음과 같이 기획 방향을 제안합니다.")

    # 인터럽트가 있으면 Payload 데이터로 덮어쓰기
    if interrupt_data:
        if "question" in interrupt_data:
            option_question = interrupt_data["question"]
        if "options" in interrupt_data:
            options = interrupt_data["options"]

    is_general = False
    if analysis_res and isinstance(analysis_res, dict):
        is_general = analysis_res.get("is_general_query", False)

    # [NEW] Router intent 확인 (greeting/info_query는 채팅 응답으로 처리)
    intent = final_result.get("intent")
    is_chat_response = intent in ("greeting", "info_query")

    # 결과 유형별 처리
    if is_chat_response:
        _handle_greeting_result(generated_plan or "안녕하세요!")
    elif options and len(options) > 0 and not is_general:
        _handle_options_result(options, option_question, analysis_res)
    elif is_general:
        _handle_general_result(analysis_res)
    elif generated_plan:
        _handle_plan_result(generated_plan, final_result, status_data)
    else:
        st.session_state.chat_history.append({
            "role": "assistant", "content": "작업이 완료되었습니다.", "type": "text"
        })


def _handle_options_result(options: list, option_question: str, analysis_res: dict):
    """옵션 선택 결과 처리"""
    preview_msg = ""
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

    msg = f"🤔 {option_question}\n\n{preview_msg}"
    msg_content = msg
    for o in options:
        msg_content += f"- **{o.get('title')}**: {o.get('description')}\n"

    st.session_state.chat_history.append({
        "role": "assistant", "content": msg_content, "type": "options"
    })


def _handle_general_result(analysis_res: dict):
    """일반 대화 응답 처리"""
    ans = analysis_res.get("general_answer", "무엇을 도와드릴까요?")
    st.session_state.chat_history.append({
        "role": "assistant", "content": ans, "type": "text"
    })
    st.session_state.generated_plan = None


def _handle_greeting_result(response: str):
    """
    인사/잡담 응답 처리 (Smart Router greeting intent)

    Router가 greeting으로 분류한 경우 호출됩니다.
    기획서 생성 없이 채팅 응답만 표시합니다.
    """
    st.session_state.chat_history.append({
        "role": "assistant", "content": response, "type": "text"
    })
    # 기획서 영역 초기화 (이전 기획서가 있어도 새 greeting에서는 표시 안 함)
    # st.session_state.generated_plan = None  # 이전 기획서는 유지


def _handle_plan_result(generated_plan: str, final_result: dict, status_data: dict = None):
    """기획서 완성 결과 처리"""
    st.session_state.generated_plan = generated_plan

    # 프리셋 및 토큰 사용량 정보
    from utils.settings import get_preset
    preset_key = st.session_state.get("generation_preset", "balanced")
    preset = get_preset(preset_key)
    usage_info = f"\n\n---\n🤖 **사용 모델**: {preset.model_type} ({preset.name})"

    token_usage = final_result.get("token_usage")
    if status_data:
        token_usage = token_usage or status_data.get("token_usage")

    if token_usage and token_usage.get("total_tokens", 0) > 0:
        usage_info += f"\n📊 **토큰 사용량**: {token_usage['total_tokens']:,}개"
        usage_info += f" (입력: {token_usage['input_tokens']:,}, 출력: {token_usage['output_tokens']:,})"
        usage_info += f"\n💰 **예상 비용**: ${token_usage['estimated_cost_usd']:.4f}"
        usage_info += f" (약 {int(token_usage['estimated_cost_krw'])}원)"

    st.session_state.chat_history.append({
        "role": "assistant",
        "content": f"✅ 기획서가 완성되었습니다!{usage_info}",
        "type": "plan"
    })

    st.session_state.trigger_notification = True

    # 히스토리 저장
    now_str = datetime.now().strftime("%H:%M:%S")
    if not st.session_state.plan_history or st.session_state.plan_history[-1]['content'] != generated_plan:
        st.session_state.plan_history.append({
            "version": len(st.session_state.plan_history) + 1,
            "timestamp": now_str,
            "content": generated_plan
        })

    # 채팅 요약 추가
    chat_summary = final_result.get("chat_summary", "")
    if chat_summary:
        st.session_state.chat_history.append({
            "role": "assistant", "content": chat_summary, "type": "summary"
        })


def run_pending_workflow(pending_text: str, status_placeholder):
    """
    대기 중인 워크플로우를 실행합니다.

    Args:
        pending_text: 사용자 입력
        status_placeholder: 상태 표시 placeholder
    """
    # Resume 명령 파싱
    resume_cmd = parse_resume_command(pending_text)

    with status_placeholder.container():
        with st.status("🚀 작업을 수행하고 있습니다...", expanded=True) as status:
            try:
                file_content = st.session_state.get("uploaded_content", None)
                current_refine_count = st.session_state.get("next_refine_count", 0)
                previous_plan = st.session_state.generated_plan
                thread_id = st.session_state.thread_id
                generation_preset = st.session_state.get("generation_preset", "balanced")

                # [NEW] API 서버 상태 확인
                api_ok, api_error = check_api_health()
                if not api_ok:
                    status.update(label="❌ API 서버 연결 실패", state="error", expanded=True)
                    st.error(f"🔌 {api_error}")
                    st.info("💡 **해결 방법:**\n- 터미널에서 서버 로그를 확인하세요\n- 앱을 새로고침하여 서버 재시작을 시도하세요")
                    return

                # API 호출
                status.write("🔄 작업 요청을 전송 중입니다...")
                
                # [NEW] 스켈레톤 로딩 표시
                skeleton_placeholder = status.empty()
                skeleton_placeholder.markdown("""
                <div style="margin: 1rem 0;">
                    <div class="skeleton skeleton-title" style="height: 1.2rem; width: 60%; margin-bottom: 0.5rem; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite; border-radius: 4px;"></div>
                    <div class="skeleton skeleton-text" style="height: 0.8rem; width: 80%; margin-bottom: 0.3rem; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite; border-radius: 4px;"></div>
                    <div class="skeleton skeleton-text" style="height: 0.8rem; width: 70%; background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%); background-size: 200% 100%; animation: shimmer 1.5s ease-in-out infinite; border-radius: 4px;"></div>
                </div>
                <style>
                    @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
                </style>
                """, unsafe_allow_html=True)
                
                execute_workflow_api(
                    pending_text, resume_cmd, thread_id,
                    generation_preset, file_content,
                    current_refine_count, previous_plan
                )

                # [FIX] Resume 후 상태가 변경될 때까지 대기
                # Background task가 시작되어 상태가 "running"으로 변경될 때까지 기다림
                if resume_cmd:
                    status.write("⏳ 재개 처리 중...")
                    for _ in range(10):  # 최대 5초 대기
                        time.sleep(0.5)
                        check_res = httpx.get(
                            f"{Config.API_BASE_URL}/workflow/status/{thread_id}",
                            timeout=5.0
                        )
                        if check_res.status_code == 200:
                            check_status = check_res.json().get("status", "")
                            if check_status == "running":
                                break  # 상태가 running으로 변경됨

                # 스켈레톤 제거
                skeleton_placeholder.empty()

                # 진행률 UI
                progress_bar = status.progress(0)
                current_step_display = status.empty()
                
                # [FIX] st.empty()로 변경 - 매번 지우고 다시 그리기
                log_placeholder = status.empty()
                visible_logs = []  # 전체 로그 저장
                
                def on_log_update(log_entry):
                    """실시간 로그 업데이트 (최근 3개만 표시, 나머지 접힘)"""
                    nonlocal visible_logs
                    visible_logs.append(log_entry)
                    
                    # placeholder 완전히 지우고 다시 렌더링
                    with log_placeholder.container():
                        # 5개 초과 시 "이전 로그 보기" 표시
                        if len(visible_logs) > 5:
                            with st.expander(f"📜 이전 단계 ({len(visible_logs) - 5}개)", expanded=False):
                                for old_log in visible_logs[:-5]:
                                    summary_short = old_log['summary'][:40] + "..." if len(old_log['summary']) > 40 else old_log['summary']
                                    st.caption(f"✓ {old_log['step']} — {summary_short}")
                        
                        # 최근 5개 로그만 표시
                        recent_logs = visible_logs[-5:]
                        for log in recent_logs:
                            st.markdown(f"**{log['icon']} {log['step'].upper()}** — {log['summary']}")

                # 폴링
                final_result, execution_log = poll_workflow_status(
                    thread_id, status, progress_bar, current_step_display,
                    on_log_callback=on_log_update  # 콜백 전달
                )

                # 완료 상태 표시
                progress_bar.progress(100)
                start_time = time.time()
                total_elapsed = int(time.time() - start_time)
                current_step_display.empty()

                if execution_log:
                    # status.markdown(f"✅ **완료** — 총 {len(execution_log)}단계 실행됨") # 중복 제거
                    pass

                status.update(label=f"✅ 완료! (총 {total_elapsed}초)", state="complete", expanded=False)

                # 결과 처리
                handle_workflow_result(final_result)

                # Mermaid 다이어그램 표시
                if final_result.get("_plan"):
                    from agents.agent_config import export_plan_to_mermaid
                    mermaid_code = export_plan_to_mermaid(final_result["_plan"])
                    if mermaid_code:
                        with st.expander("🔗 실행 계획 다이어그램 (Mermaid)", expanded=True):
                            from ui.components import render_scalable_mermaid
                            render_scalable_mermaid(mermaid_code, height=400)
                            st.caption("Supervisor가 수립하고 실행한 에이전트 협업 구조도입니다.")

                st.rerun()

            except Exception as e:
                # [DEBUG] 상세 에러 로그 출력
                import traceback
                trace_str = traceback.format_exc()
                print(f"[CRITICAL ERROR] {trace_str}") 
                with st.expander("🚨 디버그용 상세 에러 로그 (Traceback)", expanded=True):
                    st.code(trace_str)

                from ui.validation import handle_exception_friendly, detect_error_type, ERROR_MESSAGES

                handle_exception_friendly(e, context="기획서 생성 중")

                if st.session_state.current_state:
                    if isinstance(st.session_state.current_state, dict):
                        st.session_state.current_state.update({
                            "error": str(e), "step_status": "FAILED"
                        })

                error_type = detect_error_type(e)
                error_info = ERROR_MESSAGES.get(error_type, ERROR_MESSAGES[error_type.UNKNOWN])
                friendly_msg = f"{error_info['icon']} **{error_info['title']}**\n\n"
                friendly_msg += f"{error_info['message']}\n\n{error_info['hint']}"

                st.session_state.chat_history.append({
                    "role": "assistant", "content": friendly_msg, "type": "error"
                })
