"""
PlanCraft Agent - Analyzer Agent

사용자 입력을 분석하여 핵심 정보를 추출하는 Agent입니다.
충분한 정보가 없으면 추가 질문을 생성하여 워크플로우를 중단시킵니다.

주요 기능:
    - 핵심 주제 및 목적 파악
    - 타겟 사용자 식별
    - 주요 기능 추출
    - 누락된 정보 식별
    - 추가 질문 생성

입력:
    - user_input: 사용자 원본 입력
    - file_content: 참고 파일 (선택)
    - rag_context: RAG 검색 결과 (선택)

출력:
    - analysis: 분석 결과 딕셔너리
    - need_more_info: 추가 정보 필요 여부
    - questions: 추가 질문 목록

Best Practice 적용:
    - with_structured_output(): LangChain 표준 Structured Output 패턴
    - PlanCraftState 타입 어노테이션: 명시적 입출력 타입
"""

from utils.llm import get_llm
from utils.schemas import AnalysisResult
from graph.state import PlanCraftState
from prompts.analyzer_prompt import ANALYZER_SYSTEM_PROMPT, ANALYZER_USER_PROMPT


class AnalyzerAgent:
    """
    사용자 입력을 분석하고 필요한 정보를 파악하는 Agent

    LangChain의 with_structured_output()을 사용하여
    Pydantic 스키마 기반의 구조화된 출력을 생성합니다.

    Attributes:
        llm: AzureChatOpenAI 인스턴스 (Structured Output 적용)

    Example:
        >>> agent = AnalyzerAgent(model_type="gpt-4o")
        >>> state = {"user_input": "점심 추천 앱", ...}
        >>> result = agent.run(state)
        >>> print(result["analysis"]["topic"])
    """

    def __init__(self, model_type: str = "gpt-4o"):
        """
        Analyzer Agent를 초기화합니다.

        Args:
            model_type: 사용할 LLM 모델 ("gpt-4o" 또는 "gpt-4o-mini")
        """
        # 분석은 정확성이 중요하므로 낮은 temperature 사용
        base_llm = get_llm(model_type=model_type, temperature=0.3)

        # with_structured_output: LangChain Best Practice
        # - 수동 JSON 파싱 불필요
        # - Pydantic 검증 자동화
        # - 더 안정적인 출력
        self.llm = base_llm.with_structured_output(AnalysisResult)

    def run(self, state: PlanCraftState) -> PlanCraftState:
        """
        사용자 입력을 분석합니다.

        Args:
            state: 현재 워크플로우 상태 (PlanCraftState)
                - user_input: 사용자 입력 (필수)
                - file_content: 참고 파일 (선택)
                - rag_context: RAG 컨텍스트 (선택)

        Returns:
            PlanCraftState: 업데이트된 상태
                - analysis: 분석 결과
                - need_more_info: 추가 정보 필요 여부
                - options: 선택 옵션 목록
                - current_step: "analyze"
        """
        # =====================================================================
        # 1. 입력 데이터 추출
        # =====================================================================
        user_input = state.get("user_input", "")
        file_content = state.get("file_content", "")
        rag_context = state.get("rag_context", "")
        web_context = state.get("web_context", "")

        # =====================================================================
        # 2. 컨텍스트 구성
        # =====================================================================
        context_parts = []
        if file_content:
            context_parts.append(f"[참고 파일 내용]\n{file_content}")
        if web_context:
            context_parts.append(f"[웹에서 가져온 정보]\n{web_context}")
        if rag_context:
            context_parts.append(f"[기획서 작성 가이드]\n{rag_context}")
        context = "\n\n".join(context_parts) if context_parts else "없음"

        # =====================================================================
        # 3. Structured Output으로 LLM 호출
        # =====================================================================
        messages = [
            {"role": "system", "content": ANALYZER_SYSTEM_PROMPT},
            {"role": "user", "content": ANALYZER_USER_PROMPT.format(
                user_input=user_input,
                context=context
            )}
        ]

        try:
            # with_structured_output 사용: 자동으로 Pydantic 객체 반환
            analysis: AnalysisResult = self.llm.invoke(messages)
            analysis_dict = analysis.model_dump()

        except Exception as e:
            # 파싱 실패 시 기본값 반환
            analysis_dict = AnalysisResult(
                topic=user_input[:50] if user_input else "주제 미정",
                purpose="분석 필요",
                target_users="미정",
                key_features=[],
                assumptions=[],
                missing_info=[],
                options=[],
                option_question="",
                need_more_info=False
            ).model_dump()
            state["error"] = f"분석 오류: {str(e)}"

        # =====================================================================
        # 4. 상태 업데이트
        # =====================================================================
        state["analysis"] = analysis_dict
        state["need_more_info"] = analysis_dict.get("need_more_info", False)
        state["options"] = analysis_dict.get("options", [])
        state["option_question"] = analysis_dict.get("option_question", "")
        state["current_step"] = "analyze"

        return state


def run(state: PlanCraftState) -> PlanCraftState:
    """
    LangGraph 노드용 함수

    LangGraph에서 노드로 등록할 때 사용하는 래퍼 함수입니다.

    Args:
        state: 워크플로우 상태 (PlanCraftState)

    Returns:
        PlanCraftState: 업데이트된 상태
    """
    agent = AnalyzerAgent()
    return agent.run(state)
