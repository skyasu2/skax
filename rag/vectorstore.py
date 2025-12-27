"""
PlanCraft Agent - RAG 벡터스토어 모듈

FAISS를 사용하여 문서를 벡터화하고 저장/검색하는 기능을 제공합니다.
기획서 작성 가이드 문서를 임베딩하여 RAG 파이프라인에서 활용합니다.

주요 기능:
    - 문서 로딩 및 청크 분할
    - FAISS 벡터스토어 생성
    - 벡터스토어 저장/로드

파일 구조:
    rag/
    ├── documents/           # 원본 가이드 문서
    │   ├── 기획서_작성가이드.md
    │   ├── 섹션별_작성원칙.md
    │   ├── 체크리스트.md
    │   └── 좋은예시.md
    ├── faiss_index/         # 생성된 벡터 인덱스 (자동 생성)
    └── vectorstore.py       # (이 파일)

사용 예시:
    from rag.vectorstore import init_vectorstore, load_vectorstore
    
    # 초기화 (최초 1회)
    init_vectorstore()
    
    # 로드 (검색 시)
    vs = load_vectorstore()
    results = vs.similarity_search("기획서 작성법", k=3)
"""

import os
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.llm import get_embeddings

# =============================================================================
# 경로 설정
# =============================================================================
# 벡터스토어 저장 경로
VECTORSTORE_PATH = os.path.join(os.path.dirname(__file__), "faiss_index")
# 원본 문서 경로
DOCS_PATH = os.path.join(os.path.dirname(__file__), "documents")


def init_vectorstore() -> FAISS:
    """
    문서를 로드하고 FAISS 벡터스토어를 초기화합니다.
    
    documents/ 폴더의 마크다운 파일들을 읽어서
    청크로 분할하고 임베딩하여 FAISS 인덱스를 생성합니다.
    생성된 인덱스는 faiss_index/ 폴더에 저장됩니다.
    
    Returns:
        FAISS: 생성된 벡터스토어 인스턴스
    
    Example:
        >>> vs = init_vectorstore()
        >>> print("벡터스토어 초기화 완료")
    
    Note:
        - 최초 실행 시 또는 문서 업데이트 시 호출합니다.
        - Azure OpenAI Embedding API를 호출하므로 API 키가 필요합니다.
    """
    # =========================================================================
    # 1. 문서 폴더 확인
    # =========================================================================
    if not os.path.exists(DOCS_PATH):
        print(f"[WARN] Document folder not found: {DOCS_PATH}")
        return None

    print(f"[INFO] Loading documents from: {DOCS_PATH}")
    
    # =========================================================================
    # 2. 문서 로딩
    # =========================================================================
    # 마크다운 파일만 로드 (UTF-8 인코딩)
    loader = DirectoryLoader(
        DOCS_PATH, 
        glob="**/*.md", 
        loader_cls=TextLoader, 
        loader_kwargs={"encoding": "utf-8"}
    )
    raw_docs = loader.load()
    print(f"  - Documents loaded: {len(raw_docs)}")

    # =========================================================================
    # 3. 텍스트 분할 (Chunking)
    # =========================================================================
    # 마크다운 헤더를 기준으로 분할하여 문맥 유지
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,      # 청크 최대 크기
        chunk_overlap=200,    # 청크 간 중복 (문맥 연결용)
        separators=[
            "\n## ",          # H2 헤더
            "\n# ",           # H1 헤더
            "\n### ",         # H3 헤더
            "\n",             # 줄바꿈
            " ",              # 공백
            ""                # 문자
        ]
    )
    docs = text_splitter.split_documents(raw_docs)
    print(f"  - Chunks created: {len(docs)}")

    # =========================================================================
    # 4. 임베딩 및 벡터스토어 생성
    # =========================================================================
    print("  - Creating embeddings...")
    embeddings = get_embeddings()
    vectorstore = FAISS.from_documents(docs, embeddings)

    # =========================================================================
    # 5. 저장
    # =========================================================================
    vectorstore.save_local(VECTORSTORE_PATH)
    print(f"  - Vectorstore saved: {VECTORSTORE_PATH}")
    print("[OK] Vectorstore initialization complete!")
    
    return vectorstore


def load_vectorstore() -> FAISS:
    """
    저장된 FAISS 벡터스토어를 로드합니다.
    
    faiss_index/ 폴더에서 저장된 인덱스를 불러옵니다.
    인덱스가 없으면 자동으로 init_vectorstore()를 호출합니다.
    
    Returns:
        FAISS: 로드된 벡터스토어 인스턴스 (또는 None)
    
    Example:
        >>> vs = load_vectorstore()
        >>> results = vs.similarity_search("기획서 작성법", k=3)
        >>> for doc in results:
        ...     print(doc.page_content[:100])
    """
    # =========================================================================
    # 1. 저장된 인덱스 확인
    # =========================================================================
    if not os.path.exists(VECTORSTORE_PATH):
        print("[WARN] Vectorstore not found. Initializing...")
        return init_vectorstore()
    
    # =========================================================================
    # 2. 인덱스 로드
    # =========================================================================
    embeddings = get_embeddings()
    try:
        # allow_dangerous_deserialization: pickle 역직렬화 허용 (신뢰된 데이터만)
        return FAISS.load_local(
            VECTORSTORE_PATH, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
    except Exception as e:
        print(f"[WARN] Failed to load vectorstore: {e}")
        print("  -> Reinitializing...")
        return init_vectorstore()


# =============================================================================
# CLI 실행
# =============================================================================
if __name__ == "__main__":
    """
    직접 실행 시 벡터스토어를 초기화합니다.
    
    사용법:
        python -m rag.vectorstore
        또는
        python rag/vectorstore.py
    """
    print("=" * 50)
    print("PlanCraft RAG 벡터스토어 초기화")
    print("=" * 50)
    init_vectorstore()
