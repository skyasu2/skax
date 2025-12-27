"""
PlanCraft Agent - LLM 클라이언트 모듈

Azure OpenAI의 Chat 모델과 Embedding 모델을 초기화하는 유틸리티 함수를 제공합니다.
LangChain의 AzureChatOpenAI와 AzureOpenAIEmbeddings를 래핑합니다.

사용 예시:
    from utils.llm import get_llm, get_embeddings
    
    # Chat 모델 가져오기
    llm = get_llm(model_type="gpt-4o", temperature=0.7)
    response = llm.invoke("안녕하세요")
    
    # Embedding 모델 가져오기
    embeddings = get_embeddings()
    vector = embeddings.embed_query("텍스트")
"""

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from utils.config import Config


def get_llm(model_type: str = "gpt-4o", temperature: float = 0.7) -> AzureChatOpenAI:
    """
    Azure OpenAI Chat 모델 인스턴스를 생성합니다.
    
    Args:
        model_type: 사용할 모델 타입
            - "gpt-4o": GPT-4o 모델 (더 강력, 비용 높음)
            - "gpt-4o-mini": GPT-4o-mini 모델 (빠름, 비용 낮음)
        temperature: 응답의 창의성 조절 (0.0 ~ 2.0)
            - 0.0: 결정적, 일관된 응답
            - 1.0: 기본값
            - 2.0: 매우 창의적, 다양한 응답
    
    Returns:
        AzureChatOpenAI: 설정된 LLM 클라이언트 인스턴스
    
    Example:
        >>> llm = get_llm(model_type="gpt-4o-mini", temperature=0.3)
        >>> response = llm.invoke([{"role": "user", "content": "Hello"}])
        >>> print(response.content)
    
    Note:
        - Config.validate()가 먼저 호출되어야 합니다.
        - 네트워크 오류 시 예외가 발생할 수 있습니다.
    """
    # 모델 타입에 따른 배포 이름 선택
    deployment_name = Config.get_model_deployment(model_type)
    
    # AzureChatOpenAI 인스턴스 생성
    return AzureChatOpenAI(
        azure_endpoint=Config.AOAI_ENDPOINT,
        api_key=Config.AOAI_API_KEY,
        api_version=Config.AOAI_API_VERSION,
        azure_deployment=deployment_name,
        temperature=temperature
    )


def get_embeddings() -> AzureOpenAIEmbeddings:
    """
    Azure OpenAI Embedding 모델 인스턴스를 생성합니다.
    
    기본적으로 text-embedding-3-large 모델을 사용합니다.
    이 모델은 3072 차원의 고품질 임베딩을 생성합니다.
    
    Returns:
        AzureOpenAIEmbeddings: 설정된 Embedding 클라이언트 인스턴스
    
    Example:
        >>> embeddings = get_embeddings()
        >>> vector = embeddings.embed_query("기획서 작성 가이드")
        >>> print(f"벡터 차원: {len(vector)}")  # 3072
    
    Note:
        - RAG 파이프라인에서 문서 임베딩 및 쿼리 임베딩에 사용됩니다.
        - 동일한 텍스트는 항상 동일한 벡터를 생성합니다.
    """
    return AzureOpenAIEmbeddings(
        azure_endpoint=Config.AOAI_ENDPOINT,
        api_key=Config.AOAI_API_KEY,
        api_version=Config.AOAI_API_VERSION,
        azure_deployment=Config.AOAI_DEPLOY_EMBED_LARGE
    )
