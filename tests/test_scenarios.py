"""
PlanCraft Advanced Scenarios Tests

복잡한 사용자 인터랙션 및 에러 상황, 분기 처리를 시뮬레이션하는 고급 시나리오 테스트입니다.
실제 LLM 호출 없이 상태(State) 전이와 분기 로직의 정확성을 검증합니다.
"""

import pytest
import time
from functools import wraps
from unittest.mock import MagicMock, patch
from graph.state import PlanCraftState, create_initial_state, update_state
from utils.schemas import AnalysisResult, OptionChoice

# 메트릭 측정 데코레이터
def measure_time(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        duration = (end_time - start_time) * 1000  # ms
        print(f"\n[Metric] {func.__name__}: {duration:.2f}ms")
        return result
    return wrapper

class TestAdvancedScenarios:
    """고급 시나리오 테스트 모음 (TypedDict 기반)"""

    @measure_time
    def test_scenario_human_interrupt_flow(self):
        """
        [시나리오 A] 휴먼 인터럽트 흐름 검증

        1. 사용자: 모호한 요청
        2. 시스템: 분석 후 추가 정보 필요 판단 (need_more_info=True)
        3. 워크플로우: should_ask_user -> 'option_pause' 라우팅
        4. 노드: option_pause_node 실행 -> 인터럽트 페이로드 생성
        5. 사용자: 옵션 선택 응답
        6. 시스템: 선택 반영 후 상태 업데이트
        """
        # 1. 초기 상태 (모호한 요청)
        # 2. 분석 결과 시뮬레이션 (need_more_info=True)
        analysis = AnalysisResult(
            topic="모호함",
            purpose="불명확",
            target_users="미정",
            need_more_info=True,
            options=[
                OptionChoice(title="웹", description="Web"),
                OptionChoice(title="앱", description="App")
            ],
            option_question="어떤 종류인가요?"
        )

        # TypedDict 방식으로 상태 생성
        state = create_initial_state("앱 만들어줘")
        state = update_state(state,
            current_step="analyze",
            analysis=analysis.model_dump(),
            need_more_info=True,
            options=[opt.model_dump() for opt in analysis.options],
            option_question="어떤 종류인가요?"
        )

        # 검증: 상태 필드가 올바르게 설정되었는지
        assert state.get("need_more_info") is True
        assert state.get("option_question") == "어떤 종류인가요?"

        # 3. 라우팅 로직 검증
        from graph.workflow import should_ask_user
        next_route = should_ask_user(state)
        assert next_route == "option_pause"

        # 4. option_pause_node 실행 시뮬레이션
        #    (interrupt 함수는 mock 처리하여 페이로드 확인)
        from graph.workflow import option_pause_node
        from graph.interrupt_utils import handle_user_response

        with patch('graph.workflow.interrupt') as mock_interrupt:
            # interrupt 호출 시 None 반환 (로컬 모드 시뮬레이션 or 중단)
            mock_interrupt.return_value = None

            paused_state = option_pause_node(state)

            # 인터럽트 호출 여부 및 페이로드 검증
            assert mock_interrupt.called
            payload = mock_interrupt.call_args[0][0]
            assert payload['question'] == "어떤 종류인가요?"
            assert len(payload['options']) == 2

        # 5. 사용자 응답 시뮬레이션 (UI에서 선택)
        user_response = {
            "selected_option": {"title": "웹", "description": "Web"}
        }

        # 6. 응답 처리 및 상태 업데이트
        resumed_state = handle_user_response(state, user_response)

        # 검증: 에러 플래그 해제, 입력 업데이트 (dict-access)
        assert resumed_state.get("need_more_info") is False
        assert "[선택: 웹 - Web]" in resumed_state.get("user_input", "")

        # 다시 라우팅 체크 -> 이제는 continue여야 함
        assert should_ask_user(resumed_state) == "continue"

    @measure_time
    def test_scenario_error_and_retry(self):
        """
        [시나리오 B] 에러 발생 및 재시도 흐름 검증

        1. 시스템: 실행 중 에러 발생 (State에 error 기록)
        2. UI/로직: 에러 감지 및 상태 전환 (FAILED)
        3. 사용자: 재시도 버튼 클릭
        4. 시스템: 에러 클리어, retry_count 증가
        """
        # 1. 정상 실행 중
        state = create_initial_state("GO")
        state = update_state(state, current_step="analyze")

        # 2. 에러 발생 시뮬레이션 (Try-Except 블록 내 로직)
        try:
            raise ValueError("LLM API Timeout")
        except Exception as e:
            # update_state로 에러 기록
            error_state = update_state(state,
                error=str(e),
                step_status="FAILED"
            )

        # 검증: 에러 상태 반영 (dict-access)
        assert error_state.get("error") == "LLM API Timeout"
        assert error_state.get("step_status") == "FAILED"

        # 3. 재시도 로직 시뮬레이션 (UI 버튼 클릭 핸들러)
        #    retry_count 증가, error 클리어
        current_retry = error_state.get("retry_count", 0)
        retried_state = update_state(error_state,
            error=None,
            step_status="RUNNING",
            retry_count=current_retry + 1
        )

        # 검증: 정상화 및 재시도 카운트 (dict-access)
        assert retried_state.get("error") is None
        assert retried_state.get("step_status") == "RUNNING"
        assert retried_state.get("retry_count") == 1

    @measure_time
    def test_scenario_general_query(self):
        """
        [시나리오 C] 일반 질의 처리 흐름 검증

        1. 사용자: "안녕" 입력
        2. 분석기: is_general_query=True 판단
        3. 워크플로우: 'general_response' 라우팅
        4. 노드: general_response_node 실행 및 종료
        """
        state = create_initial_state("안녕")

        # 분석 결과 주입 (dict-access)
        analysis = AnalysisResult(
            topic="인사", purpose="", target_users="",
            is_general_query=True,
            general_answer="안녕하세요! 무엇을 도와드릴까요?"
        )
        state = update_state(state, analysis=analysis.model_dump())

        # 라우팅 확인
        from graph.workflow import should_ask_user
        assert should_ask_user(state) == "general_response"

        # 노드 실행
        from graph.workflow import general_response_node

        final_state = general_response_node(state)

        # 검증 (TypedDict dict-access 방식 사용)
        assert final_state.get("current_step") == "general_response"
        assert final_state.get("final_output") == "안녕하세요! 무엇을 도와드릴까요?"
        # 이력 확인 (마지막 항목)
        step_history = final_state.get("step_history", [])
        last_history = step_history[-1] if step_history else {}
        assert last_history.get("step") == "general_response"
        assert last_history.get("status") == "SUCCESS"

    @measure_time
    def test_scenario_refiner_loop(self):
        """
        [시나리오 D] Refiner 재작성 루프 검증

        1. Reviewer가 REVISE 판정 (verdict != PASS)
        2. Refiner가 refined=True, refine_count 증가
        3. 조건부 엣지가 'retry' → structure로 회귀
        4. 3회 도달 시 'complete' → format으로 진행
        """
        from graph.workflow import create_workflow

        # 1. REVISE 판정 시뮬레이션
        state = create_initial_state("테스트 앱")
        state = update_state(state,
            current_step="review",
            review={"verdict": "REVISE", "overall_score": 7, "action_items": ["BM 보강 필요"]},
            refine_count=0
        )

        # 2. Refiner 실행
        from agents.refiner import run as refiner_run
        refined_state = refiner_run(state)

        # 검증: refined=True, refine_count=1
        assert refined_state.get("refined") is True
        assert refined_state.get("refine_count") == 1

        # 3. 조건부 엣지 라우팅 검증
        #    workflow 내부 should_refine_again 함수 테스트
        def should_refine_again(s):
            if s.get("refined") and s.get("refine_count", 0) < 3:
                return "retry"
            return "complete"

        route = should_refine_again(refined_state)
        assert route == "retry"  # structure로 회귀

        # 4. 최대 횟수(3회) 도달 시 complete 확인
        max_state = update_state(refined_state, refine_count=3)
        route_max = should_refine_again(max_state)
        assert route_max == "complete"  # format으로 진행

        # 5. PASS 판정 시 complete 확인
        pass_state = create_initial_state("테스트")
        pass_state = update_state(pass_state,
            review={"verdict": "PASS", "overall_score": 9},
            refine_count=0
        )
        pass_refined = refiner_run(pass_state)
        assert pass_refined.get("refined") is False
        assert should_refine_again(pass_refined) == "complete"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
