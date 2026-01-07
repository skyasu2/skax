"""
PlanCraft Agent - 웹 검색 판단 모듈

사용자 입력에 따라 웹 검색이 필요한지 판단하고 적절한 쿼리를 생성합니다.
"""

import re
from typing import Dict, Optional
from datetime import datetime
from utils.llm import get_llm


# =============================================================================
# 프롬프트 인젝션 방어
# =============================================================================

# 위험한 프롬프트 인젝션 패턴 (대소문자 무시)
DANGEROUS_PATTERNS = [
    r"ignore\s+(above|previous|all)",
    r"disregard\s+(above|previous|all)",
    r"forget\s+(above|previous|all)",
    r"new\s+instructions?",
    r"system\s*prompt",
    r"jailbreak",
    r"pretend\s+you",
    r"act\s+as\s+if",
    r"bypass",
    r"override",
    r"\bDAN\b",  # "Do Anything Now" jailbreak
    r"ignore\s+safety",
]


def _sanitize_user_input(user_input: str) -> str:
    """
    사용자 입력을 정제하여 프롬프트 인젝션 공격을 방어합니다.

    Args:
        user_input: 원본 사용자 입력

    Returns:
        str: 정제된 입력 (위험 패턴 감지 시 빈 문자열 반환)
    """
    if not user_input:
        return ""

    # 위험한 패턴 감지
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, user_input, re.IGNORECASE):
            print(f"[WARN] 프롬프트 인젝션 패턴 감지됨: {pattern}")
            return ""  # 검색 스킵 유도

    # 제어 문자 제거 (탭, 줄바꿈은 유지)
    sanitized = ''.join(
        char for char in user_input
        if ord(char) >= 32 or char in '\n\t'
    )

    return sanitized.strip()

# =============================================================================
# 웹 검색 필요 여부 판단 키워드
# =============================================================================

# 내부 문서로 충분한 키워드 (웹 검색 불필요)
INTERNAL_KEYWORDS = [
    "규정", "매뉴얼", "절차", "프로세스", "내부",
    "사내", "우리", "당사", "회사",
]

def should_search_web(
    user_input: str,
    rag_context: str = "",
    max_queries: int = 3  # [NEW] 최대 쿼리 수 제한
) -> Dict[str, any]:
    """
    웹 검색이 필요한지 판단합니다.

    변경된 로직 (v1.4.1):
    - RAG 컨텍스트가 있어도 웹 검색을 우선적으로 수행합니다.
    - URL이 포함된 경우에만 Fetch로 넘기기 위해 검색을 스킵합니다.
    - 그 외 대부분의 기획 관련 요청에 대해 검색을 수행합니다.

    Args:
        user_input: 사용자 입력 텍스트
        rag_context: RAG에서 검색된 컨텍스트 (참고용, 스킵 기준 아님)
        max_queries: 최대 생성 쿼리 수 (기본 3개)

    Returns:
        Dict: {
            "should_search": bool,
            "reason": str,
            "search_query": str | list (검색 필요시)
        }
    """
    # 1. URL이 이미 있으면 웹 검색 불필요 (URL fetch로 처리)
    if re.search(r'https?://', user_input):
        return {
            "should_search": False,
            "reason": "URL이 직접 제공됨",
            "search_query": None
        }

    # 2. 명시적인 내부 문서 질의인 경우만 스킵
    has_internal = any(kw in user_input for kw in INTERNAL_KEYWORDS)
    if has_internal:
        return {
            "should_search": False,
            "reason": "내부 문서 질의",
            "search_query": None
        }

    # 3. 그 외 모든 경우 웹 검색 수행 (LLM 활용)
    query = _generate_search_query_with_llm(user_input, max_queries=max_queries)
    return {
        "should_search": True,
        "reason": "최신/외부 정보 보강",
        "search_query": query
    }


def _generate_search_query_with_llm(user_input: str, max_queries: int = 3) -> str:
    """
    LLM을 사용하여 최적의 검색 쿼리를 생성합니다.

    Args:
        user_input: 사용자 입력
        max_queries: 생성할 최대 쿼리 수 (기본 3)

    Returns:
        list[str]: 검색 쿼리 목록
    """
    try:
        # [보안] 프롬프트 인젝션 방어
        sanitized_input = _sanitize_user_input(user_input)
        if not sanitized_input:
            print("[WARN] 입력이 정제 후 비어있음, 검색 스킵")
            return []

        llm = get_llm(model_type="gpt-4o-mini", temperature=0.3)

        # [수정] 입력이 너무 길면 가장 최근 내용(뒤쪽) 위주로 자름 (컨텍스트 오염 방지)
        # 이전 턴의 전체 대화나 로그가 넘어올 경우를 대비해 뒷부분(최신 요청)을 우선합니다.
        if len(sanitized_input) > 2000:
            truncated_input = sanitized_input[-2000:]
        else:
            truncated_input = sanitized_input

        # [NEW] max_queries에 따라 프롬프트 조정
        if max_queries == 1:
            system_prompt = (
                "당신은 전문적인 '전략적 웹 검색 설계자'입니다. 기획서 작성을 위한 **가장 핵심적인 검색 쿼리 1개**를 설계하세요.\n\n"
                "## 핵심 검색 원칙\n"
                "- 시장 규모 및 트렌드 정보를 우선합니다.\n"
                "- 구체적인 주제명을 반드시 포함하세요.\n\n"
                "## 출력 형식 (JSON Only)\n"
                "반드시 아래 JSON 형식으로만 출력하세요.\n"
                "```json\n"
                "[\"[구체적 주제] 2026 시장 규모 및 트렌드 통계\"]\n"
                "```"
            )
        else:
            system_prompt = (
                f"당신은 전문적인 '전략적 웹 검색 설계자'입니다. 기획서 작성을 위한 **가장 효과적인 검색 쿼리 {max_queries}개**를 설계하세요.\n\n"
                "## 전략적 검색 원칙 (MECE)\n"
                "1. **시장성 검증**: 시장 규모, 성장률, 최신 트렌드, 통계\n"
                "2. **BM/수익성**: 수익 모델, 가격 정책, 비용 구조, 성공/실패 사례\n"
                "3. **실현 가능성**: 법적 규제, 기술적 제약, 경쟁 현황\n\n"
                "## 🚫 필수 제약 (Negative Constraints)\n"
                "1. **주제 집중**: 사용자 주제와 관련 없는 일반적인 산업(반도체, 탄소중립 등) 키워드는 절대 포함하지 마세요.\n"
                "2. **구체성**: '트렌드'라고 뭉뚱그리지 말고 '이동식 치과 트렌드'처럼 구체적으로 명시하세요.\n"
                "3. 만약 주제가 특정 틈새 시장(Niche)이라면, 가장 유사한 상위 시장(예: 이동식 의료 -> 방문 진료 시장)을 검색하세요.\n\n"
                "## 출력 형식 (JSON Only)\n"
                "반드시 아래 JSON 형식으로만 출력하세요. 설명은 필요 없습니다.\n"
                "```json\n"
                "[\n"
                "  \"[구체적 주제] 2026 시장 규모 및 성장률 통계\",\n"
                "  \"[구체적 주제] 성공적인 수익 모델 및 가격 정책 사례\",\n"
                "  \"[구체적 주제] 주요 법적 규제 및 기술적 제약 사항\"\n"
                "]\n"
                "```"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"주제: {truncated_input}"}
        ]

        response = llm.invoke(messages)
        content = response.content.strip()
        
        # JSON 파싱 시도
        import json
        try:
            # 마크다운 코드블록 제거
            if "```" in content:
                content = content.replace("```json", "").replace("```", "")
            
            queries = json.loads(content)
            if isinstance(queries, list) and len(queries) > 0:
                # [NEW] max_queries로 제한
                limited_queries = queries[:max_queries]
                print(f"[WebSearch] Strategic Queries Generated ({len(limited_queries)}/{max_queries}): {limited_queries}")
                return limited_queries
        except Exception:
            print(f"[WARN] 쿼리 생성 JSON 파싱 실패, 일반 텍스트로 처리: {content}")
            return [content] # 실패 시 원본 반환

        return [content] # 기본값

    except Exception as e:
        print(f"[WARN] 검색 쿼리 생성 실패: {e}")
        return [user_input[:50]]  # 실패 시 원본 리스트로 반환


def _generate_search_query_regex(user_input: str) -> str:
    """(Fallback) 정규식을 사용한 쿼리 생성"""
    # 1. 구분선 및 이전 히스토리 제거 시도 (마지막 요청만 추출)
    split_pattern = r'---\s*\[.*?\]\s*---'
    parts = re.split(split_pattern, user_input)
    
    # 분리된 것 중 가장 마지막 내용 사용 (가장 최근 요청)
    target_input = parts[-1] if parts else user_input
    
    # 2. 불필요한 조사/어미 제거
    clean_input = re.sub(r'[을를이가은는에서의로]', ' ', target_input)
    clean_input = re.sub(r'\s+', ' ', clean_input).strip()
    
    # 3. 최신 연도 추가
    current_year = datetime.now().year
    if str(current_year) not in clean_input:
        return f"{clean_input} {current_year} 트렌드"
        
    return clean_input
