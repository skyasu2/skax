"""
PlanCraft Agent - RAG Retriever 모듈

벡터스토어에서 쿼리와 관련된 문서를 검색하는 기능을 제공합니다.
LangGraph 워크플로우의 retrieve 노드에서 사용됩니다.

주요 기능:
    - 유사도 기반 문서 검색 (MMR)
    - Cross-Encoder Reranking (정확도 향상)
    - Multi-Query Retrieval (검색 재현율 향상)
    - Long Context Reorder (중요 정보 재배치)
    - 검색 결과 포맷팅

사용 예시:
    from rag.retriever import Retriever

    # 기본 검색 (MMR only)
    retriever = Retriever(k=3)
    docs = retriever.get_relevant_documents("기획서 작성법")

    # 고급 검색 (Reranking + Multi-Query + Reorder)
    retriever = Retriever(
        k=3,
        use_reranker=True,
        use_multi_query=True,
        use_context_reorder=True
    )
    docs = retriever.get_relevant_documents("기획서 작성법")
"""

from typing import List, Optional
from rag.vectorstore import load_vectorstore


class Retriever:
    """
    RAG 검색을 수행하는 클래스

    FAISS 벡터스토어에서 쿼리와 유사한 문서를 검색합니다.
    다양한 고급 기능으로 검색 품질을 향상시킬 수 있습니다.

    Attributes:
        vectorstore: FAISS 벡터스토어 인스턴스
        k: 최종 반환할 문서 수
        use_reranker: Cross-Encoder Reranking 사용 여부
        use_multi_query: Multi-Query Retrieval 사용 여부
        use_query_expansion: Query Expansion 사용 여부
        use_context_reorder: Long Context Reorder 사용 여부
        fetch_k_multiplier: 초기 검색 배수

    Example:
        >>> retriever = Retriever(k=3, use_reranker=True, use_multi_query=True)
        >>> docs = retriever.get_relevant_documents("기획서 구조")
        >>> for doc in docs:
        ...     print(doc.page_content[:50])
    """

    def __init__(
        self,
        k: int = 3,
        use_reranker: bool = False,
        use_multi_query: bool = False,
        use_query_expansion: bool = False,
        use_context_reorder: bool = False,
        fetch_k_multiplier: int = 4,
        multi_query_n: int = 3
    ):
        """
        Retriever를 초기화합니다.

        Args:
            k: 최종 반환할 상위 문서 수 (기본값: 3)
            use_reranker: Cross-Encoder Reranking 사용 여부 (기본값: False)
            use_multi_query: Multi-Query Retrieval 사용 여부 (기본값: False)
            use_query_expansion: Query Expansion 사용 여부 (기본값: False)
            use_context_reorder: Long Context Reorder 사용 여부 (기본값: False)
            fetch_k_multiplier: 초기 검색 배수 (기본값: 4)
            multi_query_n: Multi-Query 시 생성할 변형 쿼리 수 (기본값: 3)

        Note:
            - use_multi_query=True: 여러 변형 쿼리로 검색 후 통합 (재현율 향상)
            - use_reranker=True: Cross-Encoder로 정확도 향상
            - use_context_reorder=True: 중요 문서를 앞/뒤로 재배치
        """
        self.vectorstore = load_vectorstore()
        self.k = k
        self.use_reranker = use_reranker
        self.use_multi_query = use_multi_query
        self.use_query_expansion = use_query_expansion
        self.use_context_reorder = use_context_reorder
        self.fetch_k_multiplier = fetch_k_multiplier
        self.multi_query_n = multi_query_n

    def get_relevant_documents(self, query: str) -> list:
        """
        쿼리와 관련된 문서를 검색합니다.

        검색 파이프라인:
            1. [Query Expansion] 쿼리 확장 (약어, 동의어)
            2. [Multi-Query] 여러 변형 쿼리로 검색 후 통합
            3. [MMR Search] 다양성 기반 검색
            4. [Reranking] Cross-Encoder로 재정렬
            5. [Reorder] 중요 문서 앞/뒤 배치

        Args:
            query: 검색 쿼리 문자열

        Returns:
            list: Document 객체 리스트
        """
        if not self.vectorstore:
            return []

        # 1. Query Expansion (약어 확장)
        search_query = self._expand_query(query) if self.use_query_expansion else query

        # 2. Multi-Query Retrieval
        if self.use_multi_query:
            docs = self._multi_query_retrieve(search_query)
        else:
            docs = self._single_query_retrieve(search_query)

        # 3. Reranking (이미 multi_query에서 처리되거나 여기서 처리)
        if self.use_reranker and not self.use_multi_query:
            from rag.reranker import rerank_documents
            docs = rerank_documents(query, docs, top_k=self.k)

        # 4. Long Context Reorder
        if self.use_context_reorder and len(docs) > 3:
            docs = self._reorder_documents(docs)

        return docs[:self.k]

    def _expand_query(self, query: str) -> str:
        """쿼리 확장 (약어, 동의어)"""
        try:
            from rag.query_transform import expand_query
            return expand_query(query)
        except Exception as e:
            print(f"[Retriever] Query expansion 실패: {e}")
            return query

    def _multi_query_retrieve(self, query: str) -> list:
        """
        Multi-Query Retrieval

        여러 변형 쿼리로 검색 후 결과를 통합합니다.

        1. 원본 + 변형 쿼리 생성
        2. 각 쿼리로 검색
        3. 중복 제거 후 통합
        4. Reranking으로 최종 정렬
        """
        from rag.query_transform import generate_multi_queries

        # 1. 변형 쿼리 생성
        queries = generate_multi_queries(query, n=self.multi_query_n, use_llm=False)
        print(f"[Retriever] Multi-Query: {queries}")

        # 2. 각 쿼리로 검색
        all_docs = []
        seen_contents = set()

        for q in queries:
            docs = self._single_query_retrieve(q, k_override=self.k * 2)
            for doc in docs:
                # 중복 제거 (content 기반)
                content_hash = hash(doc.page_content[:200])
                if content_hash not in seen_contents:
                    seen_contents.add(content_hash)
                    all_docs.append(doc)

        # 3. Reranking으로 최종 정렬
        if self.use_reranker and all_docs:
            from rag.reranker import rerank_documents
            all_docs = rerank_documents(query, all_docs, top_k=self.k)

        return all_docs

    def _single_query_retrieve(self, query: str, k_override: int = None) -> list:
        """
        단일 쿼리로 검색

        Reranker 사용 시: 더 많은 후보 검색 후 Reranking
        Reranker 미사용 시: MMR 검색
        """
        k = k_override or self.k

        if self.use_reranker and not self.use_multi_query:
            # Reranking Mode: 더 많은 후보 검색
            from rag.reranker import rerank_documents

            fetch_k = k * self.fetch_k_multiplier
            candidates = self.vectorstore.max_marginal_relevance_search(
                query,
                k=fetch_k,
                fetch_k=fetch_k * 2,
                lambda_mult=0.7
            )
            return rerank_documents(query, candidates, top_k=k)
        else:
            # MMR Mode: 다양성 중심 검색
            return self.vectorstore.max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=k * self.fetch_k_multiplier,
                lambda_mult=0.6
            )

    def _reorder_documents(self, docs: list) -> list:
        """
        Long Context Reorder

        LLM의 "Lost in the Middle" 문제 해결을 위해
        중요한 문서를 앞과 뒤에 배치합니다.

        원본: [1위, 2위, 3위, 4위, 5위]
        재배치: [1위, 3위, 5위, 4위, 2위]
        """
        try:
            from langchain_community.document_transformers import LongContextReorder

            reordering = LongContextReorder()
            reordered = reordering.transform_documents(docs)
            return reordered
        except ImportError:
            print("[Retriever] LongContextReorder not available, skipping reorder")
            return docs
        except Exception as e:
            print(f"[Retriever] Reorder 실패: {e}")
            return docs

    def get_formatted_context(self, query: str) -> str:
        """
        쿼리와 관련된 문서를 검색하여 포맷된 문자열로 반환합니다.

        여러 문서의 내용을 하나의 문자열로 결합합니다.
        프롬프트에 컨텍스트로 삽입할 때 사용합니다.

        Args:
            query: 검색 쿼리 문자열

        Returns:
            str: 검색된 문서들의 내용을 결합한 문자열

        Example:
            >>> context = retriever.get_formatted_context("기획서 배경")
            >>> prompt = f"참고 자료:\\n{context}\\n\\n질문: ..."
        """
        docs = self.get_relevant_documents(query)

        if not docs:
            return ""

        # 각 문서 내용을 구분자로 연결
        return "\n\n---\n\n".join([d.page_content for d in docs])


# =============================================================================
# 편의 함수
# =============================================================================

def create_advanced_retriever(
    k: int = 3,
    preset: str = "balanced"
) -> Retriever:
    """
    프리셋 기반 고급 Retriever 생성

    Args:
        k: 반환할 문서 수
        preset: 프리셋 키 ("fast", "balanced", "quality")

    Returns:
        Retriever: 설정된 Retriever 인스턴스
    """
    if preset == "quality":
        return Retriever(
            k=k,
            use_reranker=True,
            use_multi_query=True,
            use_query_expansion=True,
            use_context_reorder=True
        )
    elif preset == "fast":
        return Retriever(
            k=k,
            use_reranker=False,
            use_multi_query=False,
            use_query_expansion=False,
            use_context_reorder=False
        )
    else:  # balanced
        return Retriever(
            k=k,
            use_reranker=False,
            use_multi_query=True,
            use_query_expansion=True,
            use_context_reorder=False
        )
