"""
PlanCraft - Smart Router Node

입력 전처리를 담당하는 "Rule + LLM Hybrid" 라우터입니다.
context_gathering 이전에 실행되어 불필요한 RAG/Web 검색을 방지합니다.

[핵심 설계 원칙]
1. 규칙 우선 (Fast Path): 명확한 패턴은 LLM 호출 없이 즉시 분류
2. LLM 폴백 (Uncertain Path): 모호한 입력만 LLM으로 정확하게 분류
3. 비용 최적화: 90%+ 요청을 규칙으로 처리하여 API 비용 절감

[분류 결과 (Intent)]
- greeting: 인사/잡담 → context_gathering 스킵 → 바로 general_response
- planning: 기획 요청 → context_gathering → analyze → ...
- confirmation: 이전 제안 승인 → context_gathering 스킵 → analyze
"""

from enum import Enum
from typing import Optional
from graph.state import PlanCraftState, update_state
from graph.nodes.common import update_step_history
from utils.file_logger import get_file_logger


class Intent(str, Enum):
    """사용자 입력 의도 분류"""
    GREETING = "greeting"        # 인사, 잡담, 안부
    INFO_QUERY = "info_query"    # 정보성 질문 (날씨, 뉴스, 시세 등) → 웹검색 우선
    PLANNING = "planning"        # 기획서 작성 요청 (새 기획)
    MODIFICATION = "modification"  # [NEW] 기존 기획서 수정 요청
    CONFIRMATION = "confirmation"  # 이전 제안 승인 ("좋아", "진행해")
    UNCERTAIN = "uncertain"      # 규칙으로 판단 불가 → LLM 폴백


# =============================================================================
# 규칙 기반 빠른 분류 (Zero LLM Call)
# =============================================================================

# 인사/잡담 패턴 (정확히 일치하거나 포함 시)
GREETING_EXACT = {
    "안녕", "안녕하세요", "hi", "hello", "헬로", "하이",
    "고마워", "감사합니다", "고맙습니다", "ㄱㅅ", "ㅎㅇ",
    "뭘 할 수 있어", "뭐 할 수 있어", "도움말", "help",
    "누구세요", "누구야", "소개해", "자기소개",
}

GREETING_CONTAINS = {
    "오늘 뭐해", "심심해", "잘 지내",
}

# [NEW] 정보성 질문 패턴 (웹검색 우선)
INFO_QUERY_KEYWORDS = {
    # 시사/뉴스
    "뉴스", "소식", "이슈",
    # 날씨/환경
    "날씨", "기온", "미세먼지",
    # 금융/시세
    "시세", "가격", "환율", "주가", "코인", "비트코인", "이더리움", "주식",
    # 트렌드
    "트렌드", "인기", "유행", "핫한",
    # 명시적 검색 요청
    "검색해", "찾아봐", "알아봐", "조사해",
}

# 승인/확정 패턴 (정확히 일치 또는 시작 패턴)
CONFIRMATION_EXACT = {
    "좋아", "좋습니다", "진행해", "진행", "ㅇㅇ", "ㅇ",
    "네", "예", "응", "확인", "ok", "okay", "yes",
    "그렇게 해", "그래", "알겠어", "해줘",
}

# 승인 시작 패턴 (startswith)
CONFIRMATION_STARTSWITH = {
    "네,", "네 ", "예,", "예 ", "좋아,", "좋아 ",
    "진행", "확인", "알겠"
}

# [NEW] 기획서 수정 요청 패턴 (기존 기획서가 있을 때)
MODIFICATION_KEYWORDS = {
    # 수정 동사
    "수정해", "바꿔", "고쳐", "변경해", "교체해",
    # 보완 동사
    "보완해", "추가해", "넣어", "보강해", "강화해",
    # 삭제 동사
    "삭제해", "빼", "제거해", "없애",
    # 상세화 요청
    "더 자세히", "자세하게", "구체적으로", "상세하게",
    # 요약 요청
    "요약해", "줄여", "간략하게", "핵심만",
    # 섹션 지정
    "섹션", "부분", "항목",
}

# 기획 키워드 (하나라도 포함 시 PLANNING)
PLANNING_KEYWORDS = {
    # 서비스/제품 유형
    "앱", "플랫폼", "서비스", "시스템", "웹", "사이트", "어플", "애플리케이션",
    # 사업 관련
    "기획", "사업", "창업", "스타트업", "비즈니스", "프로젝트",
    # 콘텐츠/기능
    "리뷰", "추천", "검색", "관리", "예약", "배달", "쇼핑", "커머스",
    # 동사형 요청 (새 기획용)
    "만들어", "개발", "구축", "설계", "기획해",
}


def _classify_by_rules(user_input: str, has_previous_proposal: bool) -> Intent:
    """
    규칙 기반 빠른 분류

    Args:
        user_input: 사용자 입력
        has_previous_proposal: 이전 제안(current_analysis)이 있는지 여부

    Returns:
        Intent: 분류된 의도 (UNCERTAIN이면 LLM 폴백 필요)
    """
    if not user_input:
        return Intent.UNCERTAIN

    normalized = user_input.strip().lower()
    original = user_input.strip()

    # 1단계: 정확히 일치하는 인사 패턴
    if normalized in GREETING_EXACT or original in GREETING_EXACT:
        return Intent.GREETING

    # 2단계: 이전 제안이 있고 승인 패턴인 경우
    if has_previous_proposal:
        # 정확히 일치
        if normalized in CONFIRMATION_EXACT or original in CONFIRMATION_EXACT:
            return Intent.CONFIRMATION
        # 시작 패턴
        if any(original.startswith(p) or normalized.startswith(p) for p in CONFIRMATION_STARTSWITH):
            return Intent.CONFIRMATION
        # 짧은 긍정 응답도 확인으로 처리
        if len(normalized) <= 5 and any(p in normalized for p in ["좋", "응", "ㅇ", "네", "예"]):
            return Intent.CONFIRMATION

        # [NEW] 2.5단계: 수정 요청 패턴 (기존 기획서가 있을 때만)
        if any(kw in original or kw in normalized for kw in MODIFICATION_KEYWORDS):
            return Intent.MODIFICATION

    # 3단계: 기획 키워드 포함 여부 (새 기획)
    if any(kw in original for kw in PLANNING_KEYWORDS):
        return Intent.PLANNING

    # 4단계: [NEW] 정보성 질문 (웹검색 우선)
    if any(kw in normalized for kw in INFO_QUERY_KEYWORDS):
        return Intent.INFO_QUERY

    # 5단계: 인사 포함 패턴 (키워드가 없으면서 인사 패턴 포함)
    if any(g in normalized for g in GREETING_CONTAINS):
        return Intent.GREETING

    # 6단계: 짧은 입력(5자 이하)이면서 키워드 없음 → 인사로 추정
    if len(original) <= 5:
        return Intent.GREETING

    # 규칙으로 판단 불가
    return Intent.UNCERTAIN


def _classify_by_llm(user_input: str) -> Intent:
    """
    LLM 기반 정밀 분류 (규칙으로 판단 불가한 경우에만 호출)

    Note:
        비용 최적화를 위해 최소한의 토큰만 사용합니다.
        temperature=0으로 결정론적 출력을 보장합니다.
    """
    logger = get_file_logger()

    try:
        from utils.llm import get_llm

        # 최소 프롬프트로 분류 (토큰 절약)
        prompt = f"""사용자 입력을 분류하세요. 반드시 아래 4가지 중 하나만 출력:
- greeting: 인사, 잡담, 안부, 질문 (예: "안녕", "뭐 해?", "누구야")
- planning: 앱/서비스/사업 기획 요청 (예: "배달 앱", "쇼핑몰 기획")
- modification: 기존 기획서 수정 요청 (예: "수정해줘", "더 자세히", "요약해")
- confirmation: 이전 제안 승인 (예: "좋아", "진행해")

입력: "{user_input}"
분류:"""

        llm = get_llm(temperature=0)
        response = llm.invoke(prompt)

        # 응답에서 Intent 추출
        result = response.content.strip().lower() if hasattr(response, 'content') else str(response).strip().lower()

        if "greeting" in result:
            logger.info(f"[SmartRouter] LLM 분류: GREETING for '{user_input}'")
            return Intent.GREETING
        elif "modification" in result:
            logger.info(f"[SmartRouter] LLM 분류: MODIFICATION for '{user_input}'")
            return Intent.MODIFICATION
        elif "planning" in result:
            logger.info(f"[SmartRouter] LLM 분류: PLANNING for '{user_input}'")
            return Intent.PLANNING
        elif "confirmation" in result:
            logger.info(f"[SmartRouter] LLM 분류: CONFIRMATION for '{user_input}'")
            return Intent.CONFIRMATION
        else:
            # 기본값: 기획 요청으로 처리 (False Negative 방지)
            logger.info(f"[SmartRouter] LLM 분류 불명확, PLANNING으로 처리: '{user_input}'")
            return Intent.PLANNING

    except Exception as e:
        logger.error(f"[SmartRouter] LLM 분류 실패: {e}")
        # 폴백: 기획 요청으로 처리 (안전한 기본값)
        return Intent.PLANNING


# =============================================================================
# Router Node 함수
# =============================================================================

def smart_router_node(state: PlanCraftState) -> PlanCraftState:
    """
    Smart Router 노드 - 입력 의도 분류 및 라우팅 결정

    [처리 흐름]
    1. 규칙 기반 빠른 분류 시도 (Zero LLM Call)
    2. 불확실하면 LLM 폴백
    3. 분류 결과(intent)를 state에 저장

    [라우팅 결과]
    - GREETING: context_gathering 스킵 → general_response
    - PLANNING: context_gathering 진행 → analyze → ...
    - CONFIRMATION: context_gathering 스킵 → analyze (이전 제안 승인)
    """
    import time
    start_time = time.time()
    logger = get_file_logger()

    user_input = state.get("user_input", "")
    current_analysis = state.get("analysis")  # 이전 제안 존재 여부
    final_output = state.get("final_output")  # 완성된 기획서 존재 여부

    # [UPDATE] 이전 기획서 또는 분석 결과가 있으면 수정 요청 가능
    has_previous_proposal = bool(current_analysis) or bool(final_output)

    # 1단계: 규칙 기반 분류
    intent = _classify_by_rules(user_input, has_previous_proposal)
    logger.info(f"[SmartRouter] 규칙 분류 결과: {intent.value} for '{user_input}'")

    # 2단계: 불확실하면 LLM 폴백
    if intent == Intent.UNCERTAIN:
        logger.info("[SmartRouter] 규칙 불확실, LLM 폴백 실행")
        intent = _classify_by_llm(user_input)

    # 3단계: 상태 업데이트
    new_state = update_state(
        state,
        intent=intent.value,
        current_step="router"
    )

    # 4단계: 로깅 및 히스토리
    summary = f"의도 분류: {intent.value}"
    return update_step_history(new_state, "router", "SUCCESS", summary, start_time=start_time)


def get_routing_intent(state: PlanCraftState) -> Optional[str]:
    """
    상태에서 라우팅 의도 조회

    Returns:
        "greeting" | "planning" | "confirmation" | None
    """
    return state.get("intent")
