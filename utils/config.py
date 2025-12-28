"""
PlanCraft Agent - 설정 관리 모듈

이 모듈은 Azure OpenAI API 연결에 필요한 환경변수를 로드하고 관리합니다.
.env.local 파일에서 설정을 읽어오며, 필수 변수가 없으면 예외를 발생시킵니다.

사용 예시:
    from utils.config import Config
    
    # 설정 검증
    Config.validate()
    
    # 설정 값 접근
    endpoint = Config.AOAI_ENDPOINT
    api_key = Config.AOAI_API_KEY
"""

import os
from dotenv import load_dotenv

# =============================================================================
# 환경변수 로드
# =============================================================================
# 기본 .env 파일 로드 (있으면)
load_dotenv()

# .env.local 파일 로드 (우선순위 높음, 로컬 개발용)
load_dotenv(".env.local", override=True)


class Config:
    """
    Azure OpenAI 설정 관리 클래스
    
    환경변수에서 Azure OpenAI 연결 정보를 읽어옵니다.
    모든 속성은 클래스 레벨에서 정의되어 있어 인스턴스 생성 없이 사용 가능합니다.
    
    Attributes:
        AOAI_ENDPOINT: Azure OpenAI 엔드포인트 URL
        AOAI_API_KEY: Azure OpenAI API 키
        AOAI_API_VERSION: API 버전 (기본값: 2024-02-15-preview)
        AOAI_DEPLOY_GPT4O: GPT-4o 모델 배포 이름
        AOAI_DEPLOY_GPT4O_MINI: GPT-4o-mini 모델 배포 이름
        AOAI_DEPLOY_EMBED_LARGE: text-embedding-3-large 배포 이름
        AOAI_DEPLOY_EMBED_SMALL: text-embedding-3-small 배포 이름
        AOAI_DEPLOY_EMBED_ADA: text-embedding-ada-002 배포 이름
    """
    
    # =========================================================================
    # Azure OpenAI 기본 설정
    # =========================================================================
    AOAI_ENDPOINT = os.getenv("AOAI_ENDPOINT")
    AOAI_API_KEY = os.getenv("AOAI_API_KEY")
    AOAI_API_VERSION = "2024-08-01-preview"
    
    # =========================================================================
    # 모델 배포 이름
    # =========================================================================
    AOAI_DEPLOY_GPT4O = os.getenv("AOAI_DEPLOY_GPT4O", "gpt-4o")
    AOAI_DEPLOY_GPT4O_MINI = os.getenv("AOAI_DEPLOY_GPT4O_MINI", "gpt-4o-mini")
    AOAI_DEPLOY_EMBED_LARGE = os.getenv("AOAI_DEPLOY_EMBED_3_LARGE", "text-embedding-3-large")
    AOAI_DEPLOY_EMBED_SMALL = os.getenv("AOAI_DEPLOY_EMBED_3_SMALL", "text-embedding-3-small")
    AOAI_DEPLOY_EMBED_ADA = os.getenv("AOAI_DEPLOY_EMBED_ADA", "text-embedding-ada-002")
    
    # =========================================================================
    # LangSmith 트레이싱 설정 (Observability)
    # =========================================================================
    LANGSMITH_TRACING_ENABLED = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGSMITH_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
    LANGSMITH_PROJECT = os.getenv("LANGCHAIN_PROJECT", "PlanCraft-Agent")
    
    # =========================================================================
    # MCP (Model Context Protocol) 설정
    # =========================================================================
    # MCP_ENABLED=true: 실제 MCP 프로토콜 사용 (mcp-server-fetch + tavily-mcp)
    # MCP_ENABLED=false: Fallback 모드 (requests + DuckDuckGo)
    MCP_ENABLED = os.getenv("MCP_ENABLED", "false").lower() == "true"
    
    # Fetch MCP 서버 설정
    MCP_FETCH_COMMAND = os.getenv("MCP_FETCH_COMMAND", "uvx")
    MCP_FETCH_SERVER = os.getenv("MCP_FETCH_SERVER", "mcp-server-fetch")
    
    # Tavily MCP 서버 설정 (웹 검색)
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    MCP_TAVILY_COMMAND = os.getenv("MCP_TAVILY_COMMAND", "npx")
    MCP_TAVILY_SERVER = os.getenv("MCP_TAVILY_SERVER", "tavily-mcp")
    
    @classmethod
    def setup_langsmith(cls) -> bool:
        """
        LangSmith 트레이싱을 활성화합니다.
        
        환경변수 LANGCHAIN_TRACING_V2=true와 LANGCHAIN_API_KEY가 설정되어 있으면
        자동으로 LangSmith 트레이싱이 활성화됩니다.
        
        Returns:
            bool: 트레이싱 활성화 여부
        """
        if cls.LANGSMITH_TRACING_ENABLED and cls.LANGSMITH_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = cls.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = cls.LANGSMITH_PROJECT
            return True
        return False

    @classmethod
    def validate(cls) -> None:
        """
        필수 환경변수가 설정되어 있는지 검증합니다.
        
        Raises:
            EnvironmentError: 필수 환경변수가 누락된 경우
        
        Example:
            >>> Config.validate()  # 성공 시 None 반환
            >>> Config.validate()  # 실패 시 EnvironmentError 발생
        """
        required_vars = ["AOAI_ENDPOINT", "AOAI_API_KEY"]
        missing = [var for var in required_vars if not getattr(cls, var)]
        
        if missing:
            raise EnvironmentError(
                f"필수 환경변수가 누락되었습니다: {', '.join(missing)}\n"
                f".env.local 파일을 확인하세요."
            )
    
    @classmethod
    def get_model_deployment(cls, model_type: str = "gpt-4o") -> str:
        """
        모델 타입에 해당하는 배포 이름을 반환합니다.
        
        Args:
            model_type: 모델 타입 ("gpt-4o" 또는 "gpt-4o-mini")
        
        Returns:
            해당 모델의 Azure 배포 이름
        """
        if model_type == "gpt-4o":
            return cls.AOAI_DEPLOY_GPT4O
        return cls.AOAI_DEPLOY_GPT4O_MINI
