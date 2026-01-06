"""
[DEPRECATED] Dynamic Q&A Node - Writer ReAct 패턴으로 대체됨

이 모듈은 더 이상 workflow에서 사용되지 않습니다.
Writer가 작성 중 자율적으로 도구를 호출하는 ReAct 패턴으로 대체되었습니다.

새로운 구현: agents/writer.py의 _run_with_react_loop()
새로운 도구: tools/writer_tools.py

기존 테스트 호환성을 위해 함수들은 유지됩니다.
새로운 코드에서는 이 모듈을 사용하지 마세요.

[기존 흐름 - DEPRECATED]
    structure → [data_gap_analysis] → (has_gaps?)
                    ↓ Yes                    ↓ No
            [specialist_request]         [write]
                    ↓
            [collect_responses]
                    ↓
                [write]

[새로운 흐름 - ACTIVE]
    structure → write (ReAct 내장)
               [Thought] "데이터 부족"
               [Action]  request_specialist_analysis(...)
               [Observation] {...}
               [Continue] 작성 계속
"""

from typing import List, Dict, Any, Literal, Union
from langgraph.types import Send
from graph.state import PlanCraftState, update_state
from utils.tracing import trace_node
from utils.error_handler import handle_node_error
from utils.llm import get_llm
from utils.schemas import DataGapAnalysis, DataGapRequest, SpecialistResponse
from prompts.discussion_prompt import DATA_GAP_ANALYSIS_PROMPT, SPECIALIST_QUERY_PROMPT


# =============================================================================
# Data Gap Analysis Node
# =============================================================================

@trace_node("data_gap_analysis", tags=["dynamic_qa", "analysis"])
@handle_node_error
def analyze_data_gaps(state: PlanCraftState) -> PlanCraftState:
    """
    Writer 작성 전 데이터 완전성 검사

    보유 데이터(analysis, specialist_analysis, rag_context, web_context)를
    기획서 구조(structure)와 대조하여 부족한 데이터를 식별합니다.

    Returns:
        PlanCraftState with:
        - data_gap_analysis: DataGapAnalysis 결과
        - pending_specialist_requests: 요청 목록 (있을 경우)
    """
    import json

    # 현재 보유 데이터 수집
    analysis = state.get("analysis", {})
    specialist_analysis = state.get("specialist_analysis", {})
    rag_context = state.get("rag_context", "")
    web_context = state.get("web_context", "")
    structure = state.get("structure", {})

    # 구조 정보 포맷팅
    structure_text = ""
    if structure:
        sections = structure.get("sections", []) if isinstance(structure, dict) else []
        structure_lines = []
        for s in sections:
            if isinstance(s, dict):
                name = s.get('name', '')
                desc = s.get('description', '')
            else:
                name = getattr(s, 'name', '')
                desc = getattr(s, 'description', '')
            structure_lines.append(f"- {name}: {desc}")
        structure_text = "\n".join(structure_lines)

    # Specialist 분석 요약
    specialist_text = ""
    if specialist_analysis:
        for key, value in specialist_analysis.items():
            if isinstance(value, dict) and not value.get("error"):
                specialist_text += f"\n### {key}\n{json.dumps(value, ensure_ascii=False, indent=2)[:500]}...\n"

    # LLM으로 데이터 갭 분석
    llm = get_llm(temperature=0.2)
    gap_llm = llm.with_structured_output(DataGapAnalysis)

    prompt = DATA_GAP_ANALYSIS_PROMPT.format(
        analysis=json.dumps(analysis, ensure_ascii=False, indent=2) if analysis else "없음",
        specialist_analysis=specialist_text or "없음",
        rag_context=rag_context[:1000] if rag_context else "없음",
        web_context=web_context[:1000] if web_context else "없음",
        structure=structure_text or "구조 미정의"
    )

    try:
        result: DataGapAnalysis = gap_llm.invoke([
            {"role": "system", "content": "데이터 완전성을 분석하고 부족한 데이터를 식별하세요."},
            {"role": "user", "content": prompt}
        ])

        # 요청 목록 저장
        pending_requests = []
        if result.has_gaps and result.gap_requests:
            for i, req in enumerate(result.gap_requests[:3]):  # 최대 3개
                pending_requests.append({
                    "request_id": f"gap_req_{i}",
                    "target_specialist": req.target_specialist,
                    "requesting_section": req.requesting_section,
                    "query": req.query,
                    "priority": req.priority,
                    "context": req.context
                })

        return update_state(
            state,
            data_gap_analysis=result.model_dump(),
            pending_specialist_requests=pending_requests,
            current_step="data_gap_analysis"
        )

    except Exception as e:
        print(f"[DataGapAnalysis] 분석 실패, 가정으로 진행: {e}")
        # 실패 시 갭 없음으로 처리 (작성 진행)
        return update_state(
            state,
            data_gap_analysis={"has_gaps": False, "can_proceed_with_assumptions": True},
            pending_specialist_requests=[],
            current_step="data_gap_analysis"
        )


# =============================================================================
# Specialist Request Dispatcher (Send API)
# =============================================================================

def dispatch_specialist_requests(state: PlanCraftState) -> Union[List[Send], PlanCraftState]:
    """
    데이터 갭 요청을 Specialist에게 분배 (LangGraph Send API)

    has_gaps=True이고 pending_requests가 있으면 각 Specialist에게 Send.
    그렇지 않으면 바로 write 노드로 진행.

    Returns:
        List[Send]: Specialist 요청들 (병렬 처리)
        또는 PlanCraftState: 요청 없이 바로 진행
    """
    gap_analysis = state.get("data_gap_analysis", {})
    pending_requests = state.get("pending_specialist_requests", [])

    # 데이터 갭이 없거나 가정으로 진행 가능하면 바로 write
    if not gap_analysis.get("has_gaps") or gap_analysis.get("can_proceed_with_assumptions"):
        return state

    # Specialist 요청 생성
    sends = []
    for req in pending_requests:
        specialist_id = req.get("target_specialist")
        if specialist_id:
            sends.append(Send(
                f"specialist_{specialist_id}",
                {
                    "request_id": req.get("request_id"),
                    "query": req.get("query"),
                    "requesting_section": req.get("requesting_section"),
                    "context": req.get("context"),
                    # 필요한 컨텍스트 전달
                    "service_overview": state.get("analysis", {}).get("topic", ""),
                    "existing_analysis": state.get("specialist_analysis", {}).get(f"{specialist_id}_analysis", {})
                }
            ))

    return sends if sends else state


# =============================================================================
# Specialist Response Handler
# =============================================================================

@trace_node("specialist_response", tags=["dynamic_qa", "specialist"])
def handle_specialist_response(state: PlanCraftState, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    개별 Specialist의 응답 처리

    Send API로 호출된 각 Specialist 노드에서 실행됩니다.
    요청된 데이터를 생성하여 반환합니다.

    Args:
        state: 현재 워크플로우 상태
        request_data: Send로 전달된 요청 데이터

    Returns:
        SpecialistResponse 형태의 응답
    """
    specialist_id = request_data.get("specialist_id", "unknown")
    query = request_data.get("query", "")
    requesting_section = request_data.get("requesting_section", "")
    context = request_data.get("context", "")
    service_overview = request_data.get("service_overview", "")
    existing_analysis = request_data.get("existing_analysis", {})

    llm = get_llm(temperature=0.4)

    prompt = SPECIALIST_QUERY_PROMPT.format(
        specialist_id=specialist_id,
        requesting_section=requesting_section,
        query=query,
        context=context,
        service_overview=service_overview,
        existing_analysis=str(existing_analysis)[:500]
    )

    try:
        response = llm.invoke([
            {"role": "system", "content": f"당신은 {specialist_id} 전문가입니다. 요청된 데이터를 제공하세요."},
            {"role": "user", "content": prompt}
        ])

        return {
            "request_id": request_data.get("request_id"),
            "specialist_id": specialist_id,
            "data": {"content": response.content},
            "confidence": 0.8,
            "sources": ["LLM Generated"]
        }

    except Exception as e:
        return {
            "request_id": request_data.get("request_id"),
            "specialist_id": specialist_id,
            "data": {"error": str(e)},
            "confidence": 0.0,
            "sources": []
        }


# =============================================================================
# Response Collector Node
# =============================================================================

@trace_node("collect_responses", tags=["dynamic_qa", "aggregation"])
@handle_node_error
def collect_specialist_responses(state: PlanCraftState) -> PlanCraftState:
    """
    Specialist 응답 수집 및 통합

    병렬로 처리된 Specialist 응답들을 수집하여
    specialist_analysis에 병합합니다.
    """
    # 응답 수집 (LangGraph가 자동으로 병합)
    specialist_responses = state.get("specialist_responses", [])
    current_specialist_analysis = state.get("specialist_analysis", {}) or {}

    # 응답을 specialist_analysis에 병합
    for response in specialist_responses:
        specialist_id = response.get("specialist_id")
        if specialist_id and response.get("data"):
            key = f"{specialist_id}_additional"
            current_specialist_analysis[key] = response.get("data")

    # 요청 완료 처리
    return update_state(
        state,
        specialist_analysis=current_specialist_analysis,
        pending_specialist_requests=[],
        specialist_responses=[],
        current_step="collect_responses"
    )


# =============================================================================
# Routing Functions
# =============================================================================

def should_request_specialist(state: PlanCraftState) -> Literal["request_specialist", "write"]:
    """
    Specialist 추가 요청 필요 여부 결정

    Returns:
        "request_specialist": 추가 데이터 필요
        "write": 바로 작성 진행
    """
    gap_analysis = state.get("data_gap_analysis", {})
    pending_requests = state.get("pending_specialist_requests", [])

    # 데이터 갭이 있고, 요청이 있고, 가정으로 진행 불가능할 때만 요청
    if (gap_analysis.get("has_gaps") and
        pending_requests and
        not gap_analysis.get("can_proceed_with_assumptions")):
        return "request_specialist"

    return "write"


# =============================================================================
# Specialist Node Factory (Send API용)
# =============================================================================

def create_specialist_node(specialist_id: str):
    """
    동적 Specialist 노드 생성 (Factory 패턴)

    Send API로 호출될 때 사용되는 개별 Specialist 노드를 생성합니다.

    Args:
        specialist_id: Specialist ID (market, bm, financial, risk, tech)

    Returns:
        노드 함수
    """
    def specialist_node(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """동적으로 생성된 Specialist 노드"""
        request_data["specialist_id"] = specialist_id
        return handle_specialist_response({}, request_data)

    specialist_node.__name__ = f"specialist_{specialist_id}_node"
    return specialist_node


# 미리 정의된 Specialist 노드들
specialist_market_node = create_specialist_node("market")
specialist_bm_node = create_specialist_node("bm")
specialist_financial_node = create_specialist_node("financial")
specialist_risk_node = create_specialist_node("risk")
specialist_tech_node = create_specialist_node("tech")
