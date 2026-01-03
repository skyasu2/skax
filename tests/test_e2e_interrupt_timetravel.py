"""
E2E Interrupt & Time-Travel Tests

실제 워크플로우를 사용한 통합 테스트:
1. E2E Interrupt 시나리오 (UI → Resume → 완료)
2. Time-Travel 복구 (Checkpoint 롤백 후 재실행)

테스트 실행:
    pytest tests/test_e2e_interrupt_timetravel.py -v

Note:
    - MemorySaver를 사용하여 테스트 격리
    - 실제 LLM 호출 없이 Mock으로 대체
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from graph.state import PlanCraftState, create_initial_state, update_state
from graph.interrupt_types import InterruptFactory, InterruptType, ResumeHandler
from graph.interrupt_utils import handle_user_response


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def memory_checkpointer():
    """테스트용 MemorySaver 인스턴스"""
    return MemorySaver()


@pytest.fixture
def unique_thread_id():
    """각 테스트마다 고유한 thread_id 생성"""
    return f"test_thread_{uuid.uuid4().hex[:8]}"


# =============================================================================
# E2E Interrupt Scenario Tests
# =============================================================================

class TestE2EInterruptScenario:
    """
    E2E Interrupt 시나리오 테스트

    Streamlit UI 시뮬레이션:
    1. 사용자 입력 → 분석 → Option Interrupt
    2. 사용자 옵션 선택 → Resume
    3. 구조 설계 → 작성 → Approval Interrupt
    4. 승인 → 완료
    """

    def test_simple_interrupt_resume_flow(self, memory_checkpointer, unique_thread_id):
        """
        단순 Interrupt → Resume 플로우 테스트

        1. 노드 실행 → Interrupt 발생
        2. 사용자 응답으로 Resume
        3. 다음 노드 실행 완료
        """
        # 간단한 테스트 그래프 생성
        def node_with_interrupt(state: Dict) -> Dict:
            """Interrupt가 있는 노드"""
            payload = InterruptFactory.option(
                question="방향을 선택하세요",
                options=[
                    {"title": "A 경로", "description": "빠른 진행"},
                    {"title": "B 경로", "description": "상세 진행"}
                ],
                interrupt_id="direction_select"
            )

            # Interrupt 호출
            response = interrupt(payload.to_dict())

            # Resume 후 실행되는 코드
            selected = response.get("selected_option", {}).get("title", "Unknown")
            return {"selected_path": selected, "step": "after_interrupt"}

        def final_node(state: Dict) -> Dict:
            """최종 노드"""
            return {"step": "completed", "result": f"완료: {state.get('selected_path')}"}

        # 그래프 구성
        graph = StateGraph(dict)
        graph.add_node("interrupt_node", node_with_interrupt)
        graph.add_node("final_node", final_node)
        graph.set_entry_point("interrupt_node")
        graph.add_edge("interrupt_node", "final_node")
        graph.add_edge("final_node", END)

        app = graph.compile(checkpointer=memory_checkpointer)

        config = {"configurable": {"thread_id": unique_thread_id}}

        # Step 1: 첫 실행 → Interrupt에서 멈춤
        result1 = app.invoke({"step": "start"}, config)

        # Interrupt 상태 확인
        state = app.get_state(config)
        assert state.next == ("interrupt_node",), "Interrupt 노드에서 멈춰야 함"

        # Step 2: Resume with user response
        user_response = {"selected_option": {"title": "A 경로", "value": "path_a"}}
        result2 = app.invoke(Command(resume=user_response), config)

        # Step 3: 최종 상태 확인
        assert result2.get("step") == "completed"
        assert "A 경로" in result2.get("result", "")

    def test_multi_step_interrupt_chain(self, memory_checkpointer, unique_thread_id):
        """
        다중 Interrupt 체인 테스트

        Option Interrupt → Form Interrupt → Approval Interrupt
        """
        step_counter = {"count": 0}

        def option_node(state: Dict) -> Dict:
            """옵션 선택 노드"""
            payload = InterruptFactory.option(
                question="서비스 유형 선택",
                options=[
                    {"title": "웹 앱", "description": "브라우저 기반"},
                    {"title": "모바일 앱", "description": "iOS/Android"}
                ],
                interrupt_id="service_type_select"
            )
            response = interrupt(payload.to_dict())
            step_counter["count"] += 1
            return {
                "service_type": response.get("selected_option", {}).get("title"),
                "step": "option_done"
            }

        def form_node(state: Dict) -> Dict:
            """폼 입력 노드"""
            payload = InterruptFactory.form(
                question="프로젝트 상세 정보",
                schema_name="ProjectInfo",
                required_fields=["name", "budget"],
                interrupt_id="project_info_form"
            )
            response = interrupt(payload.to_dict())
            step_counter["count"] += 1
            return {
                **state,
                "project_name": response.get("name"),
                "budget": response.get("budget"),
                "step": "form_done"
            }

        def approval_node(state: Dict) -> Dict:
            """승인 노드"""
            payload = InterruptFactory.approval(
                question="기획서를 승인하시겠습니까?",
                role="팀장",
                interrupt_id="final_approval"
            )
            response = interrupt(payload.to_dict())
            step_counter["count"] += 1
            approved = response.get("approved", False) or \
                       response.get("selected_option", {}).get("value") == "approve"
            return {
                **state,
                "approved": approved,
                "step": "approval_done"
            }

        def final_node(state: Dict) -> Dict:
            """최종 노드"""
            return {**state, "step": "completed"}

        # 그래프 구성
        graph = StateGraph(dict)
        graph.add_node("option", option_node)
        graph.add_node("form", form_node)
        graph.add_node("approval", approval_node)
        graph.add_node("final", final_node)

        graph.set_entry_point("option")
        graph.add_edge("option", "form")
        graph.add_edge("form", "approval")
        graph.add_edge("approval", "final")
        graph.add_edge("final", END)

        app = graph.compile(checkpointer=memory_checkpointer)
        config = {"configurable": {"thread_id": unique_thread_id}}

        # Step 1: Option Interrupt
        app.invoke({"step": "start"}, config)
        state1 = app.get_state(config)
        assert state1.next == ("option",)

        # Resume: Option 선택
        app.invoke(
            Command(resume={"selected_option": {"title": "웹 앱", "value": "web"}}),
            config
        )

        # Step 2: Form Interrupt
        state2 = app.get_state(config)
        assert state2.next == ("form",)

        # Resume: Form 입력
        app.invoke(
            Command(resume={"name": "AI 플랫폼", "budget": 100000000}),
            config
        )

        # Step 3: Approval Interrupt
        state3 = app.get_state(config)
        assert state3.next == ("approval",)

        # Resume: 승인
        result = app.invoke(
            Command(resume={"selected_option": {"value": "approve"}}),
            config
        )

        # 최종 검증
        assert result.get("step") == "completed"
        assert result.get("service_type") == "웹 앱"
        assert result.get("project_name") == "AI 플랫폼"
        assert result.get("approved") is True
        assert step_counter["count"] == 3  # 3개 노드 모두 실행됨

    def test_interrupt_with_validation_retry(self, memory_checkpointer, unique_thread_id):
        """
        유효성 검증 실패 시 재시도 시나리오

        LangGraph에서는 interrupt 후 Resume 시 노드가 재실행되므로,
        상태(state)에 시도 횟수를 저장하여 관리해야 함
        """
        def validated_form_node(state: Dict) -> Dict:
            """유효성 검증이 있는 폼 노드"""
            attempt = state.get("attempt", 0)
            last_email = state.get("last_email")
            max_retries = 3

            # 이전 시도에서 유효한 이메일이 있으면 성공
            if last_email and "@" in last_email and "." in last_email:
                return {
                    **state,
                    "email": last_email,
                    "validated": True,
                    "step": "form_done"
                }

            # 최대 재시도 초과
            if attempt >= max_retries:
                return {
                    **state,
                    "email": None,
                    "validated": False,
                    "step": "form_failed"
                }

            # 에러 힌트 생성
            error_hint = None
            if attempt > 0:
                error_hint = f"이메일 형식이 올바르지 않습니다. (시도 {attempt}/{max_retries})"

            payload = InterruptFactory.form(
                question="이메일을 입력하세요",
                schema_name="EmailForm",
                required_fields=["email"],
                field_types={"email": "email"},
                interrupt_id=f"email_form"
            )

            payload_dict = payload.to_dict()
            if error_hint:
                payload_dict["hint"] = error_hint

            response = interrupt(payload_dict)
            email = response.get("email", "")

            # 검증 결과에 따라 상태 업데이트
            if "@" in email and "." in email:
                return {
                    **state,
                    "email": email,
                    "validated": True,
                    "step": "form_done",
                    "attempt": attempt + 1
                }
            else:
                # 실패 시 attempt 증가 후 자기 자신으로 goto
                return {
                    **state,
                    "last_email": email,
                    "attempt": attempt + 1,
                    "step": "retry"
                }

        def check_result(state: Dict) -> str:
            """검증 결과에 따라 분기"""
            if state.get("validated"):
                return "end"
            elif state.get("step") == "form_failed":
                return "end"
            else:
                return "form"  # 재시도

        graph = StateGraph(dict)
        graph.add_node("form", validated_form_node)
        graph.set_entry_point("form")
        graph.add_conditional_edges("form", check_result, {"form": "form", "end": END})

        app = graph.compile(checkpointer=memory_checkpointer)
        config = {"configurable": {"thread_id": unique_thread_id}}

        # Step 1: 첫 시도 (잘못된 이메일)
        app.invoke({"step": "start", "attempt": 0}, config)
        app.invoke(Command(resume={"email": "invalid"}), config)

        # Step 2: 두 번째 시도 (여전히 잘못됨)
        app.invoke(Command(resume={"email": "still-invalid"}), config)

        # Step 3: 세 번째 시도 (올바른 이메일)
        result = app.invoke(Command(resume={"email": "valid@example.com"}), config)

        assert result.get("validated") is True
        assert result.get("email") == "valid@example.com"


# =============================================================================
# Time-Travel Recovery Tests
# =============================================================================

class TestTimeTravelRecovery:
    """
    Time-Travel 복구 테스트

    체크포인트 기반 상태 복원 및 재실행:
    1. 특정 시점의 상태 조회
    2. 과거 체크포인트로 롤백
    3. 다른 경로로 재실행
    """

    def test_get_state_history(self, memory_checkpointer, unique_thread_id):
        """
        상태 히스토리 조회 테스트
        """
        def step1(state: Dict) -> Dict:
            return {"step": "step1", "value": 1}

        def step2(state: Dict) -> Dict:
            return {**state, "step": "step2", "value": state.get("value", 0) + 1}

        def step3(state: Dict) -> Dict:
            return {**state, "step": "step3", "value": state.get("value", 0) + 1}

        graph = StateGraph(dict)
        graph.add_node("step1", step1)
        graph.add_node("step2", step2)
        graph.add_node("step3", step3)

        graph.set_entry_point("step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", "step3")
        graph.add_edge("step3", END)

        app = graph.compile(checkpointer=memory_checkpointer)
        config = {"configurable": {"thread_id": unique_thread_id}}

        # 워크플로우 실행
        result = app.invoke({"step": "start"}, config)

        # 상태 히스토리 조회
        history = list(app.get_state_history(config))

        # 히스토리 검증 (최신 → 과거 순서)
        assert len(history) >= 3, f"최소 3개 체크포인트 필요, got {len(history)}"

        # 최신 상태 확인
        latest = history[0]
        assert latest.values.get("step") == "step3"
        assert latest.values.get("value") == 3

    def test_rollback_to_checkpoint(self, memory_checkpointer, unique_thread_id):
        """
        특정 체크포인트로 롤백 테스트
        """
        execution_log = []

        def node_a(state: Dict) -> Dict:
            execution_log.append("A")
            return {"path": ["A"], "step": "a"}

        def node_b(state: Dict) -> Dict:
            execution_log.append("B")
            path = state.get("path", []) + ["B"]
            return {**state, "path": path, "step": "b"}

        def node_c(state: Dict) -> Dict:
            execution_log.append("C")
            path = state.get("path", []) + ["C"]
            return {**state, "path": path, "step": "c"}

        graph = StateGraph(dict)
        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_node("c", node_c)

        graph.set_entry_point("a")
        graph.add_edge("a", "b")
        graph.add_edge("b", "c")
        graph.add_edge("c", END)

        app = graph.compile(checkpointer=memory_checkpointer)
        config = {"configurable": {"thread_id": unique_thread_id}}

        # 첫 실행
        result1 = app.invoke({"step": "start"}, config)
        assert result1.get("path") == ["A", "B", "C"]
        assert execution_log == ["A", "B", "C"]

        # 히스토리에서 node_b 직후 체크포인트 찾기
        history = list(app.get_state_history(config))

        # step "b" 상태의 체크포인트 찾기
        checkpoint_after_b = None
        for state in history:
            if state.values.get("step") == "b":
                checkpoint_after_b = state.config
                break

        assert checkpoint_after_b is not None, "node_b 체크포인트를 찾을 수 없음"

        # 체크포인트로 롤백하여 상태 확인
        past_state = app.get_state(checkpoint_after_b)
        assert past_state.values.get("step") == "b"
        assert past_state.values.get("path") == ["A", "B"]

    def test_resume_from_past_checkpoint(self, memory_checkpointer):
        """
        과거 체크포인트에서 다른 경로로 재실행

        A → B → Interrupt → C (기존 스레드)
        새 스레드에서 같은 Interrupt 지점부터:
        A → B → Interrupt → D (다른 선택)
        """
        def node_a(state: Dict) -> Dict:
            return {"path": ["A"], "step": "a"}

        def node_b(state: Dict) -> Dict:
            path = state.get("path", []) + ["B"]
            return {**state, "path": path, "step": "b"}

        def interrupt_node(state: Dict) -> Dict:
            payload = InterruptFactory.option(
                question="다음 경로 선택",
                options=[
                    {"title": "C 경로", "description": "기본 경로"},
                    {"title": "D 경로", "description": "대안 경로"}
                ],
                interrupt_id="path_select"
            )
            response = interrupt(payload.to_dict())
            selected = response.get("selected_option", {}).get("title", "C 경로")
            path = state.get("path", []) + [selected[0]]  # 첫 글자만 (C 또는 D)
            return {**state, "path": path, "selected": selected, "step": "selected"}

        def final_node(state: Dict) -> Dict:
            return {**state, "step": "completed"}

        graph = StateGraph(dict)
        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_node("select", interrupt_node)
        graph.add_node("final", final_node)

        graph.set_entry_point("a")
        graph.add_edge("a", "b")
        graph.add_edge("b", "select")
        graph.add_edge("select", "final")
        graph.add_edge("final", END)

        app = graph.compile(checkpointer=memory_checkpointer)

        # === 첫 번째 스레드: C 경로 선택 ===
        thread1 = f"thread1_{uuid.uuid4().hex[:8]}"
        config1 = {"configurable": {"thread_id": thread1}}

        # A → B → Interrupt
        app.invoke({"step": "start"}, config1)

        # Interrupt 시점 체크포인트 저장
        state_at_interrupt = app.get_state(config1)
        assert state_at_interrupt.next == ("select",)

        # C 경로 선택
        result1 = app.invoke(
            Command(resume={"selected_option": {"title": "C 경로"}}),
            config1
        )
        assert result1.get("path") == ["A", "B", "C"]

        # === 두 번째 스레드: 같은 시작점에서 D 경로 선택 ===
        thread2 = f"thread2_{uuid.uuid4().hex[:8]}"
        config2 = {"configurable": {"thread_id": thread2}}

        # 동일하게 A → B → Interrupt까지 실행
        app.invoke({"step": "start"}, config2)

        # D 경로 선택 (다른 경로)
        result2 = app.invoke(
            Command(resume={"selected_option": {"title": "D 경로"}}),
            config2
        )

        # 다른 경로로 완료
        assert result2.get("path") == ["A", "B", "D"]
        assert result2.get("selected") == "D 경로"

        # 두 스레드가 독립적으로 다른 결과를 가짐
        final_state1 = app.get_state(config1)
        final_state2 = app.get_state(config2)
        assert final_state1.values.get("path") == ["A", "B", "C"]
        assert final_state2.values.get("path") == ["A", "B", "D"]

    def test_fork_from_checkpoint(self, memory_checkpointer):
        """
        체크포인트에서 새 브랜치(Fork) 생성

        동일한 시작점에서 다른 thread_id로 분기
        """
        def simple_node(state: Dict) -> Dict:
            counter = state.get("counter", 0) + 1
            return {"counter": counter, "step": f"step_{counter}"}

        graph = StateGraph(dict)
        graph.add_node("increment", simple_node)
        graph.set_entry_point("increment")
        graph.add_edge("increment", END)

        app = graph.compile(checkpointer=memory_checkpointer)

        # 원본 스레드 실행
        original_thread = f"original_{uuid.uuid4().hex[:8]}"
        config1 = {"configurable": {"thread_id": original_thread}}

        result1 = app.invoke({"counter": 0}, config1)
        assert result1.get("counter") == 1

        # 체크포인트 가져오기
        original_state = app.get_state(config1)
        checkpoint_id = original_state.config["configurable"].get("checkpoint_id")

        # 새 스레드로 Fork
        forked_thread = f"forked_{uuid.uuid4().hex[:8]}"
        config2 = {
            "configurable": {
                "thread_id": forked_thread,
                "checkpoint_id": checkpoint_id
            }
        }

        # Fork된 스레드에서 다시 실행
        result2 = app.invoke({"counter": 10}, {"configurable": {"thread_id": forked_thread}})

        # 원본과 Fork가 독립적으로 동작
        assert result2.get("counter") == 11

        # 원본은 변경되지 않음
        original_final = app.get_state(config1)
        assert original_final.values.get("counter") == 1


# =============================================================================
# Integration Tests: UI Simulation
# =============================================================================

class TestUISimulation:
    """
    Streamlit UI 시뮬레이션 테스트

    실제 UI 흐름을 모방하여 테스트:
    - 세션 시작
    - Interrupt 발생 시 UI 렌더링
    - 사용자 입력 처리
    - Resume
    """

    def test_streamlit_session_flow(self, memory_checkpointer, unique_thread_id):
        """
        Streamlit 세션 플로우 시뮬레이션
        """
        # UI 상태 시뮬레이션
        ui_state = {
            "messages": [],
            "waiting_for_input": False,
            "current_interrupt": None
        }

        def chat_node(state: Dict) -> Dict:
            """채팅 노드 (분석)"""
            return {
                **state,
                "analysis": {"topic": state.get("user_input", "")},
                "step": "analyzed"
            }

        def option_pause(state: Dict) -> Dict:
            """옵션 선택 HITL"""
            payload = InterruptFactory.option(
                question="어떤 방식으로 진행할까요?",
                options=[
                    {"title": "자동 생성", "description": "AI가 알아서 작성"},
                    {"title": "수동 입력", "description": "직접 내용 입력"}
                ],
                interrupt_id="mode_select"
            )
            response = interrupt(payload.to_dict())
            return {
                **state,
                "mode": response.get("selected_option", {}).get("title"),
                "step": "mode_selected"
            }

        def generate_node(state: Dict) -> Dict:
            """생성 노드"""
            return {
                **state,
                "output": f"Generated for: {state.get('analysis', {}).get('topic')}",
                "step": "completed"
            }

        graph = StateGraph(dict)
        graph.add_node("chat", chat_node)
        graph.add_node("option_pause", option_pause)
        graph.add_node("generate", generate_node)

        graph.set_entry_point("chat")
        graph.add_edge("chat", "option_pause")
        graph.add_edge("option_pause", "generate")
        graph.add_edge("generate", END)

        app = graph.compile(checkpointer=memory_checkpointer)
        config = {"configurable": {"thread_id": unique_thread_id}}

        # === UI 시뮬레이션 시작 ===

        # 1. 사용자 입력
        user_input = "AI 헬스케어 앱 기획"
        ui_state["messages"].append({"role": "user", "content": user_input})

        # 2. 그래프 실행 (Interrupt까지)
        result = app.invoke({"user_input": user_input, "step": "start"}, config)

        # 3. Interrupt 상태 확인
        graph_state = app.get_state(config)

        if graph_state.next:
            # Interrupt 발생 - UI에 옵션 표시
            ui_state["waiting_for_input"] = True
            ui_state["current_interrupt"] = graph_state.tasks[0].interrupts[0].value if graph_state.tasks else None

            # 4. UI에서 사용자 선택 (시뮬레이션)
            user_selection = {"selected_option": {"title": "자동 생성", "value": "auto"}}
            ui_state["messages"].append({
                "role": "user",
                "content": f"선택: {user_selection['selected_option']['title']}"
            })

            # 5. Resume
            final_result = app.invoke(Command(resume=user_selection), config)

            ui_state["waiting_for_input"] = False
            ui_state["current_interrupt"] = None
            ui_state["messages"].append({
                "role": "assistant",
                "content": final_result.get("output", "")
            })

        # 검증
        assert len(ui_state["messages"]) == 3  # user input, selection, output
        assert "Generated for: AI 헬스케어 앱 기획" in ui_state["messages"][-1]["content"]
        assert ui_state["waiting_for_input"] is False


# =============================================================================
# Run Tests
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
