"""
PlanCraft Agent - RAG Query Transformer 모듈

검색 전 쿼리를 변형하여 검색 품질을 향상시킵니다.

주요 기능:
    - Query Expansion: 약어 확장, 동의어 추가
    - Query Rewriting: 모호한 쿼리를 명확하게 재작성
    - Multi-Query Generation: 여러 관점의 쿼리 생성

사용 예시:
    from rag.query_transform import QueryTransformer

    transformer = QueryTransformer()

    # 쿼리 확장
    expanded = transformer.expand_query("BM 작성법")
    # -> "비즈니스 모델 수익 구조 설계 작성 방법"

    # 멀티 쿼리 생성
    queries = transformer.generate_multi_queries("기획서 배경", n=3)
    # -> ["기획서 프로젝트 배경", "기획 목적 및 동기", "서비스 필요성"]
"""

from typing import List, Optional
from functools import lru_cache


# =============================================================================
# 약어/동의어 매핑 (LLM 호출 없이 빠른 확장)
# =============================================================================
ABBREVIATION_MAP = {
    "BM": "비즈니스 모델",
    "BP": "비즈니스 플랜",
    "IR": "투자 유치",
    "MVP": "최소 기능 제품",
    "UX": "사용자 경험",
    "UI": "사용자 인터페이스",
    "KPI": "핵심 성과 지표",
    "ROI": "투자 수익률",
    "TAM": "전체 시장 규모",
    "SAM": "유효 시장 규모",
    "SOM": "수익 가능 시장",
    "B2B": "기업간 거래",
    "B2C": "기업 소비자간 거래",
    "SaaS": "서비스형 소프트웨어",
    "API": "응용 프로그램 인터페이스",
}

SYNONYM_MAP = {
    "작성법": ["작성 방법", "쓰는 법", "작성 가이드"],
    "기획서": ["기획 문서", "사업 계획서", "제안서"],
    "배경": ["목적", "필요성", "동기", "Why"],
    "목표": ["목적", "비전", "Goal"],
    "시장": ["마켓", "시장 규모", "타겟 시장"],
    "경쟁": ["경쟁사", "경쟁 분석", "Competitor"],
    "수익": ["매출", "수익 모델", "Revenue"],
}


class QueryTransformer:
    """
    검색 쿼리 변형기

    검색 품질 향상을 위해 쿼리를 다양한 방식으로 변형합니다.

    Attributes:
        use_llm: LLM 기반 변형 사용 여부 (기본 True)
        llm: LLM 인스턴스 (Lazy Loading)

    Example:
        >>> transformer = QueryTransformer()
        >>> expanded = transformer.expand_query("BM 작성법")
        >>> print(expanded)  # "비즈니스 모델 작성 방법"
    """

    def __init__(self, use_llm: bool = True):
        """
        QueryTransformer 초기화

        Args:
            use_llm: LLM 기반 변형 사용 여부 (기본 True)
                    False면 규칙 기반 변형만 사용 (빠름, 비용 없음)
        """
        self.use_llm = use_llm
        self._llm = None

    @property
    def llm(self):
        """LLM 인스턴스 Lazy Loading"""
        if self._llm is None and self.use_llm:
            try:
                from utils.llm import get_llm
                # 비용 절감을 위해 mini 모델 사용
                self._llm = get_llm(model_type="gpt-4o-mini", temperature=0.3)
            except Exception as e:
                print(f"[QueryTransformer] LLM 로드 실패: {e}")
                self.use_llm = False
        return self._llm

    def expand_query(self, query: str) -> str:
        """
        쿼리 확장: 약어 확장 + 동의어 추가

        Args:
            query: 원본 검색 쿼리

        Returns:
            str: 확장된 쿼리

        Example:
            >>> expand_query("BM 작성법")
            "비즈니스 모델 작성 방법"
        """
        expanded = query

        # 1. 약어 확장 (규칙 기반)
        for abbr, full in ABBREVIATION_MAP.items():
            if abbr in expanded:
                expanded = expanded.replace(abbr, full)

        # 2. 동의어 추가 (첫 번째 동의어만)
        for word, synonyms in SYNONYM_MAP.items():
            if word in expanded and synonyms:
                # 원본 유지하면서 동의어 추가
                expanded = expanded.replace(word, f"{word} {synonyms[0]}")
                break  # 하나만 추가

        return expanded.strip()

    def generate_multi_queries(self, query: str, n: int = 3) -> List[str]:
        """
        여러 관점의 쿼리 생성 (Multi-Query Retriever용)

        Args:
            query: 원본 검색 쿼리
            n: 생성할 변형 쿼리 수 (기본 3)

        Returns:
            List[str]: 변형 쿼리 리스트 (원본 포함)

        Example:
            >>> generate_multi_queries("기획서 배경", n=3)
            ["기획서 배경", "프로젝트 목적", "서비스 필요성"]
        """
        queries = [query]  # 원본 포함

        # 1. 규칙 기반 변형 추가
        expanded = self.expand_query(query)
        if expanded != query:
            queries.append(expanded)

        # 2. 동의어 기반 변형
        for word, synonyms in SYNONYM_MAP.items():
            if word in query:
                for syn in synonyms[:2]:  # 상위 2개 동의어만
                    variant = query.replace(word, syn)
                    if variant not in queries:
                        queries.append(variant)
                        if len(queries) >= n + 1:  # 원본 + n개
                            break

        # 3. LLM 기반 변형 (필요시)
        if self.use_llm and len(queries) < n + 1:
            llm_variants = self._generate_llm_variants(query, n - len(queries) + 1)
            for v in llm_variants:
                if v not in queries:
                    queries.append(v)

        return queries[:n + 1]  # 원본 + n개

    def _generate_llm_variants(self, query: str, n: int) -> List[str]:
        """LLM으로 쿼리 변형 생성"""
        if not self.llm:
            return []

        try:
            prompt = f"""기획서 작성 맥락에서 다음 검색 쿼리의 변형을 {n}개 생성하세요.
- 동의어, 관점 전환, 구체화 등 다양한 방식 사용
- 한 줄에 하나씩, 번호 없이 출력

원본 쿼리: {query}

변형 쿼리:"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            # 줄바꿈으로 분리하여 리스트로 변환
            variants = [line.strip() for line in content.strip().split('\n') if line.strip()]
            return variants[:n]

        except Exception as e:
            print(f"[QueryTransformer] LLM 변형 생성 실패: {e}")
            return []

    def rewrite_query(self, query: str) -> str:
        """
        모호한 쿼리를 명확하게 재작성

        Args:
            query: 원본 쿼리

        Returns:
            str: 재작성된 쿼리 (실패 시 원본 반환)
        """
        # 짧은 쿼리만 재작성 (긴 쿼리는 이미 명확함)
        if len(query) > 20 or not self.use_llm:
            return self.expand_query(query)

        if not self.llm:
            return self.expand_query(query)

        try:
            prompt = f"""기획서 작성 맥락에서 다음 검색 쿼리를 더 명확하게 재작성하세요.
- 약어를 풀어쓰기
- 모호한 표현을 구체화
- 검색에 유리한 키워드 포함

원본: {query}
재작성:"""

            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            rewritten = content.strip().split('\n')[0].strip()

            return rewritten if rewritten else self.expand_query(query)

        except Exception as e:
            print(f"[QueryTransformer] 쿼리 재작성 실패: {e}")
            return self.expand_query(query)


# =============================================================================
# 편의 함수
# =============================================================================

@lru_cache(maxsize=1)
def get_query_transformer(use_llm: bool = True) -> QueryTransformer:
    """전역 QueryTransformer 인스턴스 반환 (싱글톤)"""
    return QueryTransformer(use_llm=use_llm)


def expand_query(query: str) -> str:
    """쿼리 확장 편의 함수"""
    return get_query_transformer(use_llm=False).expand_query(query)


def generate_multi_queries(query: str, n: int = 3, use_llm: bool = True) -> List[str]:
    """멀티 쿼리 생성 편의 함수"""
    return get_query_transformer(use_llm=use_llm).generate_multi_queries(query, n)
