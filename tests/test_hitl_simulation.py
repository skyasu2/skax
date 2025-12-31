"""
e2e_hitl_test.py

LangGraph의 핵심 기능인 Human-in-the-loop (Interrupt & Resume) 및 
Time Travel을 실제 앱 로직(Mock LLM)과 함께 검증하는 E2E 테스트입니다.

Features:
1. MemorySaver를 이용한 인메모리 테스트 (빠른 실행)
2. Interrupt 발생 검증 (실제 멈추는지)
3. Resume(Command) 실행 검증 (제대로 재개되는지)
4. State Forking 검증 (과거로 돌아가서 다른 선택하기)
"""

import pytest
from unittest.mock import MagicMock, patch
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import compile_workflow
from graph.state import create_initial_state
from utils.schemas import AnalysisResult, OptionChoice

# =============================================================================
# Mocks
# =============================================================================

@pytest.fixture
def mock_llm_chain():
    """LLM 체인 Mocking (비용 절감)"""
    with patch("agents.analyzer._get_analyzer_llm") as mock_get_llm:
        mock_chain = MagicMock()
        mock_get_llm.return_value = mock_chain
        
        # Analyzer 결과 Mock (옵션 선택을 유도하도록 설정)
        mock_chain.invoke.return_value = AnalysisResult(
            topic="테스트 주제",
            purpose="테스트 목적",
            target_users="테스터",
            need_more_info=True,  # [중요] 인터럽트 유발
            options=[
                OptionChoice(title="옵션A", description="설명A"),
                OptionChoice(title="옵션B", description="설명B")
            ],
            option_question="어디로 갈까요?"
        )
        yield mock_chain

@pytest.fixture
def test_app():
    """Mock 체크포인터가 주입된 테스트용 앱"""
    memory = MemorySaver()
    # 의존성 주입 (Dependency Injection) 활용
    app = compile_workflow(use_subgraphs=False, checkpointer=memory)
    return app

# =============================================================================
# Tests
# =============================================================================

def test_hitl_interrupt_and_resume(test_app, mock_llm_chain):
    """
    [E2E] 인터럽트 발생 및 재개 테스트
    
    Flow:
    1. Analyzer 실행 -> need_more_info=True -> 'option_pause' 노드 도달
    2. Interrupt 발생 확인 (실행 멈춤)
    3. Resume (옵션A 선택) -> 실행 재개 -> 'analyze' 재실행 -> 'structure' 진행
    """
    thread_id = "test_hitl_thread_1"
    config = {"configurable": {"thread_id": thread_id}}
    
    # 1. 초기 실행
    inputs = {
        "user_input": "기획해줘",
        "thread_id": thread_id
    }
    
    # 첫 번째 실행 (여기서 멈춰야 함)
    # until="option_pause" 옵션이나 stream을 써도 되지만, interrupt가 발생하면 자동 멈춤.
    print("\n[Test] 1. 실행 시작...")
    
    # analyze -> should_ask_user(option_pause) -> option_pause_node(interrupt)
    # interrupt가 발생하면 앱 실행이 종료되고 마지막 상태가 저장됨.
    try:
        # stream 대신 invoke 사용 시 interrupt에서 멈추고 결과를 반환하지 않거나 
        # 마지막 스냅샷 상태로 종료됨. (LangGraph 버전에 따라 상이하나 최신은 멈춤)
        # 확인을 위해 list(app.stream(...))을 사용
        events = list(test_app.stream(inputs, config=config))
    except Exception as e:
        print(f"Execution stopped as expected? {e}")

    # 2. 상태 확인 (멈췄는지)
    snapshot = test_app.get_state(config)
    print(f"\n[Test] 2. 스냅샷 확인: Next={snapshot.next}")
    
    # 다음 실행할 노드가 있는지, 그리고 tasks에 interrupt가 있는지 확인
    assert snapshot.next, "실행이 완전히 끝나지 않았어야 함 (Next step 존재)"
    
    # [Check] 현재 option_pause 상태인지 확인
    # 구조상: option_pause_node는 실행되다가 interrupt()에서 멈춤.
    # 따라서 next는 없거나, tasks 속 내부에 interrupt 정보가 있어야 함.
    # LangGraph 최신 스펙: tasks[0].interrupts에 정보가 있음.
    
    task = snapshot.tasks[0]
    assert len(task.interrupts) > 0, "인터럽트가 발생해야 함"
    interrupt_value = task.interrupts[0].value
    
    print(f"[Test] 인터럽트 페이로드: {interrupt_value}")
    assert interrupt_value["type"] == "option_selector"
    assert interrupt_value["question"] == "어디로 갈까요?"
    
    # 3. Resume (재개)
    print("\n[Test] 3. Resume (옵션 선택)...")
    from langgraph.types import Command
    
    resume_payload = {
        "selected_option": {"title": "옵션A", "description": "설명A"}
    }
    
    # Command(resume=...)를 사용하여 재개
    # option_pause_node는 resume 값을 받아서 update_state 후 'analyze'로 이동하도록 되어있음
    
    # Mock LLM의 응답을 바꿔줘야 함 (안그러면 또 물어봄)
    # Analyzer가 두 번째 호출될 때는 need_more_info=False여야 무한루프 안돔.
    # side_effect를 사용하여 첫 호출, 두 번째 호출 다르게 설정
    
    mock_llm_chain.invoke.side_effect = [
        # 첫 번째 호출 (위에서 이미 소비됨)
        AnalysisResult(need_more_info=True, options=[], option_question=""), 
        # 두 번째 호출 (Resume 후) -> 이제 정보 충분
        AnalysisResult(
            topic="옵션A 기반 기획", 
            need_more_info=False, # 진행!
            is_general_query=False
        )
    ]
    
    # *중요*: Mock 객체의 side_effect는 iterator이므로 위에서 이미 한 번 호출됨.
    # 다시 설정해줘야 함.
    mock_llm_chain.invoke.side_effect = [
         AnalysisResult(
            topic="옵션A 기반 기획", 
            need_more_info=False
        )
    ]
    
    # Resume 실행
    events_resume = list(test_app.stream(
        Command(resume=resume_payload), 
        config=config
    ))
    
    # 4. 최종 결과 확인
    final_snapshot = test_app.get_state(config)
    print(f"\n[Test] 4. 최종 상태: {final_snapshot.values.get('current_step')}")
    
    # 'analyze' -> 'structure' -> ... 진행되었어야 함
    # mock_llm만 세팅했으므로 structure 등 뒷단은 에러가 날 수 있음 (Mock 안했으므로).
    # 하지만 적어도 option_pause 루프는 탈출했어야 함.
    
    # 히스토리 확인
    history = final_snapshot.values.get("step_history", [])
    # [HITL Resume] 로그가 있어야 함
    resume_logs = [h for h in history if h.get("event_type") == "HUMAN_RESPONSE"]
    assert len(resume_logs) > 0, "HUMAN_RESPONSE 로그가 기록되어야 함"
    print(f"[Test] Resume Log: {resume_logs[0]}")


def test_time_travel_forking(test_app, mock_llm_chain):
    """
    [E2E] Time Travel (Forking) 테스트
    
    Flow:
    1. 인터럽트 지점까지 실행
    2. 옵션A로 진행
    3. 다시 인터럽트 지점으로 '되감기' (Time Travel)
    4. 옵션B로 진행 (Fork) -> 다른 결과 확인
    """
    thread_id = "test_fork_thread_1"
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"user_input": "기획해줘", "thread_id": thread_id}
    
    # 1. 인터럽트 지점 도달
    try:
        list(test_app.stream(inputs, config=config))
    except: pass
    
    # 현재 체크포인트 ID 저장 (분기점)
    snapshot = test_app.get_state(config)
    fork_checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
    print(f"\n[Test] 분기점 Checkpoint ID: {fork_checkpoint_id}")
    
    # 2. 경로 A 진행
    mock_llm_chain.invoke.side_effect = [AnalysisResult(topic="Plan A", need_more_info=False)]
    
    from langgraph.types import Command
    list(test_app.stream(
        Command(resume={"selected_option": {"title": "Option A"}}), 
        config=config
    ))
    
    state_a = test_app.get_state(config)
    print(f"[Test] 경로 A 결과: {state_a.values.get('analysis', {}).get('topic')}")
    assert state_a.values["analysis"]["topic"] == "Plan A"
    
    # 3. Time Travel (되감기)
    # 분기점 체크포인트로 돌아가서 실행
    # LangGraph에서는 config의 checkpoint_id를 지정하여 invoke/stream 하면 
    # 해당 시점부터 Fork하여 새 버전이 생성됨.
    
    fork_config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": fork_checkpoint_id
        }
    }
    
    print("\n[Test] 3. Time Travel (되감기 및 경로 B 선택)...")
    
    # 경로 B 진행 (Mock 응답 변경)
    mock_llm_chain.invoke.side_effect = [AnalysisResult(topic="Plan B", need_more_info=False)]
    
    # Resume with different option
    list(test_app.stream(
        Command(resume={"selected_option": {"title": "Option B"}}), 
        config=fork_config # <-- 과거 시점 config 사용
    ))
    
    state_b = test_app.get_state(config) # 최신 상태 (B 경로의 최신)
    print(f"[Test] 경로 B 결과: {state_b.values.get('analysis', {}).get('topic')}")
    assert state_b.values["analysis"]["topic"] == "Plan B"
    
    # A와 B가 다른지 확인
    assert state_a.values["analysis"]["topic"] != state_b.values["analysis"]["topic"]
    print("\n[Success] Time Travel을 통한 경로 분기 검증 완료!")

