"""
PlanCraft Agent - 웹 검색 결과 캐싱

세션 기반 검색 결과 캐싱으로 동일 쿼리 중복 호출을 방지합니다.
- LRU 방식으로 메모리 관리
- MD5 해시 기반 키 생성
- TTL 없음 (세션 종료 시 자동 초기화)

사용법:
    from tools.search_cache import get_cached_search, cache_search_result

    # 캐시 조회
    cached = get_cached_search("피트니스 앱 시장 규모")
    if cached:
        return cached

    # 검색 수행 후 캐싱
    result = perform_search(query)
    cache_search_result(query, result)
"""

from hashlib import md5
from typing import Dict, Any, Optional
from collections import OrderedDict


class SearchCache:
    """
    LRU 기반 검색 결과 캐시

    동일 쿼리에 대한 중복 API 호출을 방지하여 비용을 절감합니다.
    OrderedDict를 사용하여 LRU(Least Recently Used) 방식으로 관리합니다.

    Attributes:
        max_size: 최대 캐시 항목 수 (기본: 50)
        _cache: OrderedDict 기반 캐시 저장소

    Example:
        >>> cache = SearchCache(max_size=10)
        >>> cache.set("query1", {"results": [...]})
        >>> cache.get("query1")
        {"results": [...]}
    """

    def __init__(self, max_size: int = 50):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str) -> str:
        """쿼리 문자열을 MD5 해시 키로 변환"""
        normalized = query.strip().lower()
        return md5(normalized.encode()).hexdigest()

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """
        캐시에서 검색 결과 조회

        Args:
            query: 검색 쿼리 문자열

        Returns:
            캐시된 결과 (없으면 None)
        """
        key = self._make_key(query)
        if key in self._cache:
            # LRU: 최근 사용으로 이동
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, query: str, result: Dict[str, Any]) -> None:
        """
        검색 결과를 캐시에 저장

        Args:
            query: 검색 쿼리 문자열
            result: 저장할 검색 결과
        """
        key = self._make_key(query)

        # 이미 있으면 업데이트 후 최근으로 이동
        if key in self._cache:
            self._cache[key] = result
            self._cache.move_to_end(key)
            return

        # 용량 초과 시 가장 오래된 항목 제거 (LRU)
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = result

    def clear(self) -> None:
        """캐시 초기화"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """캐시 통계 반환"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# =============================================================================
# 전역 캐시 인스턴스 (싱글톤)
# =============================================================================

_search_cache: Optional[SearchCache] = None


def get_search_cache() -> SearchCache:
    """전역 검색 캐시 인스턴스 반환"""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchCache()
    return _search_cache


def get_cached_search(query: str) -> Optional[Dict[str, Any]]:
    """
    캐시된 검색 결과 조회 (편의 함수)

    Args:
        query: 검색 쿼리

    Returns:
        캐시된 결과 또는 None
    """
    return get_search_cache().get(query)


def cache_search_result(query: str, result: Dict[str, Any]) -> None:
    """
    검색 결과 캐싱 (편의 함수)

    Args:
        query: 검색 쿼리
        result: 캐싱할 결과
    """
    get_search_cache().set(query, result)


def clear_search_cache() -> None:
    """검색 캐시 초기화 (편의 함수)"""
    get_search_cache().clear()


def get_cache_stats() -> Dict[str, Any]:
    """캐시 통계 조회 (편의 함수)"""
    return get_search_cache().stats()
