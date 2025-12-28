"""
PlanCraft Agent - 웹 검색 판단 모듈

사용자 입력에 따라 웹 검색이 필요한지 판단하고 적절한 쿼리를 생성합니다.
"""

import re
from typing import Dict, Optional
from datetime import datetime
from utils.llm import get_llm

# =============================================================================
# 웹 검색 필요 여부 판단 키워드
# =============================================================================

# 내부 문서로 충분한 키워드 (웹 검색 불필요)
INTERNAL_KEYWORDS = [
    "규정", "매뉴얼", "절차", "프로세스", "내부",
    "사내", "우리", "당사", "회사",
]

def should_search_web(user_input: str, rag_context: str = "") -> Dict[str, any]:
    """
    웹 검색이 필요한지 판단합니다.

    변경된 로직 (v1.4.1):
    - RAG 컨텍스트가 있어도 웹 검색을 우선적으로 수행합니다.
    - URL이 포함된 경우에만 Fetch로 넘기기 위해 검색을 스킵합니다.
    - 그 외 대부분의 기획 관련 요청에 대해 검색을 수행합니다.

    Args:
        user_input: 사용자 입력 텍스트
        rag_context: RAG에서 검색된 컨텍스트 (참고용, 스킵 기준 아님)

    Returns:
        Dict: {
            "should_search": bool,
            "reason": str,
            "search_query": str (검색 필요시)
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
    query = _generate_search_query_with_llm(user_input)
    return {
        "should_search": True,
        "reason": "최신/외부 정보 보강",
        "search_query": query
    }


def _generate_search_query_with_llm(user_input: str) -> str:
    """LLM을 사용하여 최적의 검색 쿼리를 생성합니다."""
    try:
        llm = get_llm(model_type="gpt-4o-mini", temperature=0.3)
        
        # [수정] 입력이 너무 길면 가장 최근 내용(뒤쪽) 위주로 자름 (컨텍스트 오염 방지)
        # 이전 턴의 전체 대화나 로그가 넘어올 경우를 대비해 뒷부분(최신 요청)을 우선합니다.
        if len(user_input) > 2000:
            truncated_input = user_input[-2000:]
        else:
            truncated_input = user_input

        system_prompt = (
            "당신은 전문적인 '웹 검색 키워드 추출기'입니다. 주어진 텍스트에서 기획서 작성에 필요한 핵심 주제를 파악하여 검색 쿼리를 생성하세요.\n\n"
            "## 지침\n"
            "1. 사용자의 **가장 최근 요구사항**에 집중하세요. (텍스트 중간의 '---' 구분선 등이 있다면 그 뒤의 내용을 우선함)\n"
            "2. '기획서', '작성', '도와줘', '추천해줘' 같은 **일반적인 명령어는 모두 제거**하세요.\n"
            "3. 오직 **[핵심 주제] + [시장 규모/트렌드/통계/사례]** 형태의 구체적인 키워드 조합으로 변환하세요.\n"
            "4. 주제를 파악할 수 없거나 무의미한 입력(단순 인사, 부호 등)이면 'NO_QUERY'라고만 답하세요.\n\n"
            "## 예시\n"
            "- 입력: '은퇴한 노부부를 위한 실버타운 플랫폼 기획해줘'\n"
            "- 출력: 프리미엄 실버타운 매칭 플랫폼 시장 규모 트렌드\n\n"
            "- 입력: '유튜브 숏폼 자동 편집기 만들어줘'\n"
            "- 출력: AI 숏폼 자동 편집 SaaS 시장 분석 경쟁사\n\n"
            "- 입력: 'ㅋㅋㅋ 안녕'\n"
            "- 출력: NO_QUERY"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": truncated_input}
        ]
        
        response = llm.invoke(messages)
        query = response.content.strip()
        
        # 쿼리가 유효하지 않으면 빈 문자열 반환 (검색 스킵 유도)
        if query == "NO_QUERY" or not query or len(query) < 2:
            return ""
            
        # 최신 연도 보정
        current_year = datetime.now().year
        if str(current_year) not in query and str(current_year+1) not in query:
             query += f" {current_year}"
             
        return query

    except Exception as e:
        print(f"[WARN] LLM 쿼리 생성 실패: {e}, Regex Fallback 사용")
        return _generate_search_query_regex(user_input)


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
