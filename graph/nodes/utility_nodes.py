"""
Utility Nodes for PlanCraft

[Chat Response Node]
LLM 기반 자연스러운 대화 응답을 제공합니다.
사용자와 브레인스토밍하며 아이디어를 발전시키고,
적절한 시점에 기획서 작성을 제안합니다.
"""
from graph.state import PlanCraftState, update_state
from graph.nodes.common import update_step_history
from utils.file_logger import get_file_logger


# =============================================================================
# Chat Response 시스템 프롬프트
# =============================================================================

CHAT_SYSTEM_PROMPT_TEMPLATE = """당신은 PlanCraft의 친근한 AI 어시스턴트입니다.

[오늘 날짜]
{today_date}

[당신에 대해]
- PlanCraft 기획 도우미 (GPT-4 기반)
- 자신의 모델이나 버전에 대해 추측하지 마세요

[웹 검색 결과 활용]
- 메시지에 [참고: 웹 검색 결과]가 포함되어 있으면 반드시 그 정보를 활용하여 답변하세요
- 검색 결과를 자연스럽게 요약하여 사용자에게 전달하세요
- 검색 결과가 없는 경우에만 "모른다"고 답변하세요

[역할]
- 사용자와 자연스럽게 대화하며 아이디어를 함께 발전시킵니다
- 브레인스토밍을 도와주고, 질문을 통해 아이디어를 구체화합니다
- 적절한 시점에 "기획서를 작성해 드릴까요?"라고 제안합니다

[대화 스타일]
- 친근하고 공감하는 톤 (반말도 OK)
- 짧고 핵심적인 응답 (2-4문장)
- 이모지 적절히 사용 (과하지 않게)
- 사용자 아이디어에 대한 긍정적 피드백

[기획서 제안 조건]
다음 중 하나라도 해당되면 기획서 작성을 제안하세요:
- 구체적인 서비스/앱/사업 아이디어가 언급됨
- 사용자가 "어떻게 하면 좋을까?" 류의 질문을 함
- 대화가 2-3회 이상 진행되어 아이디어가 어느 정도 구체화됨

[제안 예시]
"오, 좋은 아이디어네요! 🎯 이 내용으로 기획서를 작성해 드릴까요?"
"구체적인 방향이 잡힌 것 같아요. 본격적으로 기획서로 정리해볼까요?"

[주의사항]
- 기획서 작성 요청이 아닌 일반 대화에만 이 역할을 수행합니다
- 너무 길게 설명하지 마세요
- 사용자가 아직 탐색 중이면 강요하지 마세요"""


# 인사 응답 템플릿 (폴백용)
GREETING_RESPONSES = {
    "default": "안녕하세요! PlanCraft입니다. 🎯\n\n어떤 앱/서비스/사업을 기획해 드릴까요?\n예시: \"배달 앱\", \"독서 모임 플랫폼\", \"카페 창업\"",
    "help": "무엇을 도와드릴까요?\n\n저는 다음과 같은 기획서를 작성할 수 있어요:\n• 웹/앱 서비스 기획서\n• 사업 계획서\n• 플랫폼 구축 기획서\n\n아이디어를 말씀해주세요!",
    "thanks": "천만에요! 다른 기획이 필요하시면 언제든 말씀해주세요. 😊"
}


def general_response_node(state: PlanCraftState) -> PlanCraftState:
    """
    일반 질의 응답 노드

    [호출 경로]
    1. Router → greeting_response (intent=greeting): 인사/잡담
    2. Analyzer → general_response (is_general_query=True): Analyzer 판단 잡담

    analysis가 있으면 general_answer 사용, 없으면 기본 인사 응답.
    """
    user_input = state.get("user_input", "").lower()
    intent = state.get("intent")
    analysis = state.get("analysis")

    # 응답 결정 우선순위:
    # 1. analysis.general_answer (Analyzer가 생성한 응답)
    # 2. intent 기반 기본 응답 (Router 경로)
    answer = None

    # Analyzer 응답이 있으면 사용
    if analysis:
        if isinstance(analysis, dict):
            answer = analysis.get("general_answer")
        else:
            answer = getattr(analysis, "general_answer", None)

    # Analyzer 응답이 없으면 intent/키워드 기반 기본 응답
    if not answer:
        if "고마" in user_input or "감사" in user_input:
            answer = GREETING_RESPONSES["thanks"]
        elif "도움" in user_input or "help" in user_input or "뭘 할 수" in user_input:
            answer = GREETING_RESPONSES["help"]
        else:
            answer = GREETING_RESPONSES["default"]

    new_state = update_state(
        state,
        current_step="general_response",
        final_output=answer,
        # [FIX] greeting 경로에서 필요한 필드 설정
        need_more_info=False,
        options=[],
        option_question=None
    )

    return update_step_history(
        new_state,
        "general_response",
        "SUCCESS",
        summary=f"응답 완료 (intent={intent or 'analyzer'})"
    )


# =============================================================================
# Chat Response Node (LLM 기반)
# =============================================================================

# FAQ 캐시 (LLM 호출 없이 즉시 응답)
# 키: 포함 패턴, 값: 응답 (callable이면 동적 생성)
FAQ_CACHE = {
    # 날짜/시간 관련 (동적)
    "오늘 며칠": lambda now: f"오늘은 {now.year}년 {now.month}월 {now.day}일이야! 📅",
    "몇 시": lambda now: f"지금은 {now.hour}시 {now.minute}분이야! ⏰",
    "무슨 요일": lambda now: f"오늘은 {['월','화','수','목','금','토','일'][now.weekday()]}요일이야!",

    # 자기 소개
    "너 누구": "나는 PlanCraft 기획 도우미야! 앱, 서비스, 사업 기획서를 만들어줄 수 있어. 😊",
    "누구야": "나는 PlanCraft 기획 도우미야! 앱, 서비스, 사업 기획서를 만들어줄 수 있어. 😊",
    "뭘 할 수 있": "앱 기획, 서비스 기획, 사업 계획서 작성을 도와줄 수 있어! 아이디어를 말해줘. 🎯",
    "무엇을 할 수": "앱 기획, 서비스 기획, 사업 계획서 작성을 도와줄 수 있어! 아이디어를 말해줘. 🎯",

    # 인사
    "잘 지내": "잘 지내고 있어! 너는 어때? 오늘 기획할 아이디어 있어? 😊",
    "심심해": "심심하면 같이 아이디어 브레인스토밍 해볼까? 🤔",
}


def _check_faq_cache(user_input: str) -> str | None:
    """FAQ 캐시에서 응답 확인 (LLM 호출 스킵)"""
    from datetime import datetime
    now = datetime.now()
    input_lower = user_input.lower()

    for pattern, response in FAQ_CACHE.items():
        if pattern in input_lower:
            if callable(response):
                return response(now)
            return response
    return None


# 웹 검색이 필요할 수 있는 키워드 패턴
WEB_SEARCH_TRIGGERS = [
    "뉴스", "최신", "현재", "요즘", "트렌드", "시세", "가격", "환율",
    "날씨", "주가", "코인", "비트코인", "이더리움",
    "검색해", "찾아", "알아봐", "조사해",
    "누구", "무엇", "언제", "어디", "어떻게", "왜",  # 5W1H (선택적)
]


def _should_web_search(user_input: str) -> bool:
    """웹 검색이 필요한지 간단히 판단"""
    input_lower = user_input.lower()
    # 명시적 검색 요청 또는 시사/정보 관련 키워드
    explicit_triggers = ["검색해", "찾아봐", "알아봐", "조사해", "뉴스", "최신", "현재", "시세", "가격", "환율", "날씨", "주가", "주식", "코인", "비트코인", "이더리움", "리플", "암호화폐"]
    return any(trigger in input_lower for trigger in explicit_triggers)


def _do_quick_search(query: str) -> str:
    """빠른 웹 검색 수행 (1회)"""
    logger = get_file_logger()
    try:
        from tools.mcp_client import search_sync
        logger.info(f"[ChatResponse] 웹 검색 시작: '{query}'")
        result = search_sync(query, max_results=3, search_depth="basic")

        # 상세 로깅 추가
        success = result.get("success", False)
        source = result.get("source", "unknown")
        results_count = len(result.get("results", []))
        logger.info(f"[ChatResponse] 웹 검색 결과: success={success}, source={source}, results={results_count}")

        if not success:
            error_msg = result.get("error", "Unknown error")
            logger.warning(f"[ChatResponse] 웹 검색 실패: {error_msg}")
            return ""

        if result.get("results"):
            snippets = []
            for r in result["results"][:3]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")[:200]
                snippets.append(f"- {title}: {snippet}")
            return "\n".join(snippets)
        else:
            logger.warning("[ChatResponse] 웹 검색 결과가 비어있음")
            return ""
    except Exception as e:
        logger.error(f"[ChatResponse] 웹 검색 예외: {e}")
    return ""


def chat_response_node(state: PlanCraftState) -> PlanCraftState:
    """
    LLM 기반 자연스러운 대화 응답 노드

    [특징]
    - GPT-4o-mini 사용 (비용 효율적)
    - 대화 이력 참조하여 맥락 유지
    - 브레인스토밍 지원
    - 적절한 시점에 기획서 작성 제안
    - 필요시 웹 검색 1회 수행

    [호출 경로]
    Router → intent="greeting" → chat_response (LLM 대화)
    """
    import time
    start_time = time.time()
    logger = get_file_logger()

    user_input = state.get("user_input", "")
    chat_history = state.get("chat_history", [])

    logger.info(f"[ChatResponse] 대화 요청: '{user_input[:50]}...'")

    # [NEW] FAQ 캐시 체크 (LLM 호출 스킵)
    cached_response = _check_faq_cache(user_input)
    if cached_response:
        logger.info(f"[ChatResponse] FAQ 캐시 히트! LLM 스킵")
        new_state = update_state(
            state,
            current_step="chat_response",
            final_output=cached_response,
            need_more_info=False,
            options=[],
            option_question=None
        )
        return update_step_history(
            new_state,
            "chat_response",
            "SUCCESS",
            summary="FAQ 캐시 응답",
            start_time=start_time
        )

    try:
        from utils.llm import get_llm
        from datetime import datetime

        # 시스템 프롬프트에 현재 날짜 삽입
        weekdays_kr = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        now = datetime.now()
        today_str = f"{now.year}년 {now.month}월 {now.day}일 ({weekdays_kr[now.weekday()]})"
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(today_date=today_str)

        # 웹 검색이 필요한지 판단
        web_context = ""
        if _should_web_search(user_input):
            logger.info(f"[ChatResponse] 웹 검색 트리거됨: '{user_input[:30]}...'")
            web_context = _do_quick_search(user_input)
            if web_context:
                logger.info(f"[ChatResponse] 웹 검색 결과 추가됨 ({len(web_context)}자)")

        # 대화 이력 구성 (최근 6개까지)
        messages = [{"role": "system", "content": system_prompt}]

        # 이전 대화 추가 (맥락 유지)
        recent_history = chat_history[-6:] if len(chat_history) > 6 else chat_history
        for msg in recent_history:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg.get("content", "")
                })

        # 현재 입력 추가 (웹 검색 결과 포함)
        if web_context:
            user_message = f"{user_input}\n\n[참고: 웹 검색 결과]\n{web_context}"
        else:
            user_message = user_input
        messages.append({"role": "user", "content": user_message})

        # LLM 호출 (gpt-4o-mini로 비용 절감)
        llm = get_llm(model_type="gpt-4o-mini", temperature=0.7)
        response = llm.invoke(messages)

        answer = response.content if hasattr(response, 'content') else str(response)
        logger.info(f"[ChatResponse] 응답 생성 완료 ({len(answer)}자)")

    except Exception as e:
        logger.error(f"[ChatResponse] LLM 호출 실패: {e}")
        # 폴백: 기본 응답
        answer = GREETING_RESPONSES["default"]

    new_state = update_state(
        state,
        current_step="chat_response",
        final_output=answer,
        need_more_info=False,
        options=[],
        option_question=None
    )

    return update_step_history(
        new_state,
        "chat_response",
        "SUCCESS",
        summary="LLM 대화 응답",
        start_time=start_time
    )
