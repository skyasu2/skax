"""
PlanCraft - Writer ReAct 패턴용 도구 정의

Writer가 작성 중 자율적으로 호출할 수 있는 도구들입니다.
- request_specialist_analysis: 전문 에이전트에게 추가 분석 요청
- search_rag_documents: 내부 RAG 문서 검색
- search_web: 웹 검색

사용 예시:
    [Thought] "시장 규모 데이터가 부족하다"
    [Action]  request_specialist_analysis(specialist_type="market", query="TAM/SAM/SOM 분석")
    [Observation] {tam: "10조원", ...}
"""

from typing import Literal, Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field


# =============================================================================
# Tool Input Schemas
# =============================================================================

class SpecialistQueryInput(BaseModel):
    """Specialist 에이전트 쿼리 입력 스키마"""
    specialist_type: Literal["market", "bm", "financial", "risk", "tech"] = Field(
        description="호출할 전문 에이전트 유형: market(시장분석), bm(비즈니스모델), financial(재무), risk(리스크), tech(기술)"
    )
    query: str = Field(
        description="구체적인 질문 (예: '피트니스 앱 시장의 TAM/SAM/SOM 분석 필요')"
    )
    context: str = Field(
        default="",
        description="현재 작성 중인 섹션 또는 서비스 개요 컨텍스트"
    )


class RAGSearchInput(BaseModel):
    """RAG 검색 쿼리 입력 스키마"""
    query: str = Field(
        description="검색할 내용 (예: '비즈니스 모델 캔버스 작성 가이드')"
    )


class WebSearchInput(BaseModel):
    """웹 검색 쿼리 입력 스키마"""
    query: str = Field(
        description="검색할 내용 (예: '2024 피트니스 앱 시장 규모 통계')"
    )


# =============================================================================
# Tool Definitions
# =============================================================================

@tool(args_schema=SpecialistQueryInput)
def request_specialist_analysis(
    specialist_type: str,
    query: str,
    context: str = ""
) -> str:
    """
    전문 에이전트에게 추가 분석을 요청합니다.

    시장 규모, 경쟁사 분석, 수익 모델, 재무 계획, 리스크 분석 등
    특정 섹션 작성에 필요한 전문 데이터가 부족할 때 사용합니다.

    Examples:
        - 시장 규모 데이터 부족 → specialist_type="market", query="TAM/SAM/SOM 분석"
        - 수익 모델 다각화 필요 → specialist_type="bm", query="수익 모델 분석"
        - 재무 추정 근거 필요 → specialist_type="financial", query="초기 투자 비용 산정"
        - 리스크 식별 필요 → specialist_type="risk", query="운영 리스크 분석"

    Args:
        specialist_type: 전문 에이전트 유형 (market, bm, financial, risk, tech)
        query: 구체적인 질문
        context: 현재 작성 중인 섹션 컨텍스트

    Returns:
        전문 에이전트의 분석 결과 (마크다운 형식)
    """
    from agents.agent_config import create_agent
    from utils.file_logger import get_file_logger

    logger = get_file_logger()
    logger.info(f"[Writer ReAct] Specialist 호출: {specialist_type} - {query[:50]}...")

    try:
        agent = create_agent(specialist_type)
        if agent is None:
            return f"[ERROR] '{specialist_type}' 에이전트를 찾을 수 없습니다. 사용 가능: market, bm, financial, risk, tech"

        # 에이전트 실행
        result = agent.run(
            service_overview=context or query,
            target_market=query if specialist_type == "market" else "",
            target_users=query if specialist_type in ["bm", "content"] else ""
        )

        # 결과를 마크다운으로 포맷팅
        if hasattr(agent, 'format_as_markdown'):
            formatted = agent.format_as_markdown(result)
            logger.info(f"[Writer ReAct] Specialist 응답 완료: {len(formatted)}자")
            return formatted

        # 딕셔너리를 문자열로 변환
        if isinstance(result, dict):
            import json
            return json.dumps(result, ensure_ascii=False, indent=2)

        return str(result)

    except Exception as e:
        logger.error(f"[Writer ReAct] Specialist 호출 실패: {e}")
        return f"[ERROR] {specialist_type} 분석 실패: {str(e)}. 가정으로 진행하세요."


@tool(args_schema=RAGSearchInput)
def search_rag_documents(query: str) -> str:
    """
    내부 문서(RAG)에서 관련 정보를 검색합니다.

    기획서 작성 가이드, KPI 사전, 비즈니스 모델 사례 등
    내부 지식 베이스에서 참고 자료가 필요할 때 사용합니다.

    Examples:
        - "비즈니스 모델 캔버스 작성 가이드"
        - "KPI 지표 정의 및 측정 방법"
        - "성공적인 스타트업 사례"

    Args:
        query: 검색할 내용

    Returns:
        관련 문서 내용 (마크다운 형식)
    """
    from utils.file_logger import get_file_logger

    logger = get_file_logger()
    logger.info(f"[Writer ReAct] RAG 검색: {query[:50]}...")

    try:
        from rag.retriever import Retriever

        retriever = Retriever(k=3)
        context = retriever.get_formatted_context(query)

        if context and context.strip():
            logger.info(f"[Writer ReAct] RAG 검색 완료: {len(context)}자")
            return context
        else:
            return "[INFO] 관련 문서를 찾지 못했습니다. 일반적인 지식을 활용하세요."

    except Exception as e:
        logger.error(f"[Writer ReAct] RAG 검색 실패: {e}")
        return f"[ERROR] RAG 검색 실패: {str(e)}. 일반적인 지식을 활용하세요."


@tool(args_schema=WebSearchInput)
def search_web(query: str) -> str:
    """
    웹에서 최신 정보를 검색합니다.

    시장 통계, 경쟁사 현황, 최신 트렌드 등
    실시간 외부 데이터가 필요할 때 사용합니다.

    Examples:
        - "2024 피트니스 앱 시장 규모 통계"
        - "배달 앱 경쟁사 현황"
        - "스마트팜 기술 트렌드"

    Args:
        query: 검색할 내용

    Returns:
        검색 결과 요약 (마크다운 형식)
    """
    from utils.file_logger import get_file_logger

    logger = get_file_logger()
    logger.info(f"[Writer ReAct] 웹 검색: {query[:50]}...")

    try:
        from tools.search_client import get_search_client

        client = get_search_client()
        result = client.search(query)

        if result and result.strip():
            logger.info(f"[Writer ReAct] 웹 검색 완료: {len(result)}자")
            return result
        else:
            return "[INFO] 검색 결과가 없습니다. 일반적인 지식을 활용하세요."

    except Exception as e:
        logger.error(f"[Writer ReAct] 웹 검색 실패: {e}")
        return f"[ERROR] 웹 검색 실패: {str(e)}. 일반적인 지식을 활용하세요."


# =============================================================================
# Tool Registry
# =============================================================================

WRITER_TOOLS = [
    request_specialist_analysis,
    search_rag_documents,
    search_web,
]


def get_writer_tools():
    """
    Writer ReAct 패턴용 도구 목록을 반환합니다.

    Returns:
        List[Tool]: Writer가 사용할 수 있는 도구 목록
    """
    return WRITER_TOOLS


def get_writer_tool_descriptions() -> str:
    """
    Writer 프롬프트에 포함할 도구 설명을 반환합니다.

    Returns:
        str: 도구 설명 마크다운
    """
    descriptions = []
    for tool in WRITER_TOOLS:
        descriptions.append(f"- **{tool.name}**: {tool.description.split('.')[0]}")
    return "\n".join(descriptions)
