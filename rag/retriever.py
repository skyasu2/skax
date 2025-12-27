"""
PlanCraft Agent - RAG Retriever 모듈

벡터스토어에서 쿼리와 관련된 문서를 검색하는 기능을 제공합니다.
LangGraph 워크플로우의 retrieve 노드에서 사용됩니다.

주요 기능:
    - 유사도 기반 문서 검색
    - 검색 결과 포맷팅

사용 예시:
    from rag.retriever import Retriever
    
    retriever = Retriever(k=3)
    docs = retriever.get_relevant_documents("기획서 작성법")
    context = retriever.get_formatted_context("기획서 작성법")
"""

from rag.vectorstore import load_vectorstore


class Retriever:
    """
    RAG 검색을 수행하는 클래스
    
    FAISS 벡터스토어에서 쿼리와 유사한 문서를 검색합니다.
    
    Attributes:
        vectorstore: FAISS 벡터스토어 인스턴스
        k: 검색할 문서 수
    
    Example:
        >>> retriever = Retriever(k=3)
        >>> docs = retriever.get_relevant_documents("기획서 구조")
        >>> for doc in docs:
        ...     print(doc.page_content[:50])
    """
    
    def __init__(self, k: int = 3):
        """
        Retriever를 초기화합니다.
        
        Args:
            k: 검색할 상위 문서 수 (기본값: 3)
        
        Note:
            초기화 시 벡터스토어를 로드합니다.
            벡터스토어가 없으면 None이 됩니다.
        """
        self.vectorstore = load_vectorstore()
        self.k = k

    def get_relevant_documents(self, query: str) -> list:
        """
        쿼리와 관련된 문서를 검색합니다.
        
        Args:
            query: 검색 쿼리 문자열
        
        Returns:
            list: Document 객체 리스트
                - 각 Document는 page_content와 metadata를 포함
        
        Example:
            >>> docs = retriever.get_relevant_documents("목표 섹션 작성법")
            >>> print(docs[0].page_content)
        """
        if not self.vectorstore:
            return []
        
        # 유사도 검색 수행
        docs = self.vectorstore.similarity_search(query, k=self.k)
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
