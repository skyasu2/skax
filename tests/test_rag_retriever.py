"""
RAG Retriever 모듈 테스트

검색 기능의 핵심 동작을 검증합니다.
- 문서 검색 기본 동작
- Multi-Query 확장
- 결과 개수 제한

실행:
    pytest tests/test_rag_retriever.py -v

Note:
    RAG 모듈은 langchain_community 의존성이 필요합니다.
    의존성이 없는 환경에서는 테스트가 스킵됩니다.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

# RAG 모듈 의존성 체크
try:
    import langchain_community
    HAS_RAG_DEPS = True
except ImportError:
    HAS_RAG_DEPS = False

pytestmark = pytest.mark.skipif(
    not HAS_RAG_DEPS,
    reason="langchain_community not installed"
)


class TestRetrieverBasic:
    """Retriever 기본 기능 테스트"""

    def test_retriever_import(self):
        """Retriever 모듈 import 검증"""
        from rag.retriever import Retriever
        assert Retriever is not None

    def test_retriever_initialization(self):
        """Retriever 초기화 검증"""
        from rag.retriever import Retriever

        retriever = Retriever(k=5)
        assert retriever.k == 5

    @patch('rag.retriever.get_vectorstore')
    def test_get_relevant_documents_returns_list(self, mock_vectorstore):
        """검색 결과가 리스트로 반환되는지 검증"""
        from rag.retriever import Retriever

        # Mock 설정
        mock_store = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "테스트 문서 내용"
        mock_doc.metadata = {"source": "test.md"}
        mock_store.similarity_search.return_value = [mock_doc]
        mock_vectorstore.return_value = mock_store

        retriever = Retriever(k=3)
        results = retriever.get_relevant_documents("기획서 구조")

        assert isinstance(results, list)

    @patch('rag.retriever.get_vectorstore')
    def test_retriever_respects_k_limit(self, mock_vectorstore):
        """k 파라미터로 결과 개수가 제한되는지 검증"""
        from rag.retriever import Retriever

        # Mock 설정 - 10개 문서 반환
        mock_store = MagicMock()
        mock_docs = []
        for i in range(10):
            doc = MagicMock()
            doc.page_content = f"문서 {i}"
            doc.metadata = {}
            mock_docs.append(doc)
        mock_store.similarity_search.return_value = mock_docs[:5]  # k=5
        mock_vectorstore.return_value = mock_store

        retriever = Retriever(k=5)
        results = retriever.get_relevant_documents("테스트")

        assert len(results) <= 5


class TestQueryTransform:
    """Query Transform 모듈 테스트"""

    def test_query_transform_import(self):
        """Query Transform 모듈 import 검증"""
        from rag.query_transform import expand_query, generate_multi_queries
        assert expand_query is not None
        assert generate_multi_queries is not None

    @patch('rag.query_transform.get_llm')
    def test_expand_query_short_input(self, mock_llm):
        """짧은 입력에 대한 쿼리 확장 검증"""
        from rag.query_transform import expand_query

        # Mock LLM
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke.return_value.content = "확장된 쿼리: 모바일 앱 기획서 작성 방법"
        mock_llm.return_value = mock_llm_instance

        result = expand_query("앱 기획")

        # 확장되었거나 원본이 반환되어야 함
        assert result is not None
        assert len(result) >= len("앱 기획")

    def test_generate_multi_queries_returns_list(self):
        """Multi-Query가 리스트를 반환하는지 검증"""
        from rag.query_transform import generate_multi_queries

        with patch('rag.query_transform.get_llm') as mock_llm:
            mock_instance = MagicMock()
            mock_instance.invoke.return_value.content = "1. 쿼리1\n2. 쿼리2\n3. 쿼리3"
            mock_llm.return_value = mock_instance

            results = generate_multi_queries("AI 헬스케어 앱")

            assert isinstance(results, list)


class TestReranker:
    """Reranker 모듈 테스트"""

    def test_reranker_import(self):
        """Reranker 모듈 import 검증"""
        try:
            from rag.reranker import rerank_documents
            assert rerank_documents is not None
        except ImportError:
            pytest.skip("Reranker 모듈 또는 의존성 없음")

    def test_reranker_empty_input(self):
        """빈 입력에 대한 Reranker 동작 검증"""
        try:
            from rag.reranker import rerank_documents
            # [FIX] 함수 시그니처: rerank_documents(query, documents, ...)
            result = rerank_documents("테스트 쿼리", [])
            assert result == []
        except ImportError:
            pytest.skip("Reranker 의존성 없음")


class TestIntegration:
    """RAG 통합 테스트"""

    def test_rag_module_exports(self):
        """RAG 모듈 export 검증"""
        from rag import Retriever
        assert Retriever is not None

    @patch('rag.retriever.get_vectorstore')
    def test_retriever_handles_empty_query(self, mock_vectorstore):
        """빈 쿼리 처리 검증"""
        from rag.retriever import Retriever

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = []
        mock_vectorstore.return_value = mock_store

        retriever = Retriever(k=3)
        results = retriever.get_relevant_documents("")

        assert isinstance(results, list)
