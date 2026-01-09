"""
PlanCraft - Runtime Context Manager

애플리케이션의 런타임 상태(동적 포트, API URL 등)를 관리하는 싱글톤 클래스입니다.
전역 변수 직접 수정을 피하고 의존성 주입 패턴을 지원하기 위해 도입되었습니다.
"""
import threading
from typing import Optional

class RuntimeContext:
    """
    런타임 실행 컨텍스트 (Singleton)
    
    동적으로 할당되는 포트나 런타임에 결정되는 설정값들을 스레드 안전하게 관리합니다.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        # 기본값 설정
        self._api_port: int = 8000
        self._api_base_url: str = "http://127.0.0.1:8000/api/v1"

    @classmethod
    def get_instance(cls) -> "RuntimeContext":
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def api_base_url(self) -> str:
        """현재 활성화된 API Base URL 반환"""
        return self._api_base_url

    def set_api_port(self, port: int) -> None:
        """
        API 포트 설정 및 URL 갱신
        
        Args:
            port: 실행된 FastAPI 서버의 포트 번호
        """
        self._api_port = port
        self._api_base_url = f"http://127.0.0.1:{port}/api/v1"
        
        # [Legacy Support] Config 객체 동기화
        # 기존 코드와의 호환성을 위해 Config 클래스 변수도 업데이트합니다.
        # 추후 모든 참조가 RuntimeContext를 통하도록 리팩토링되면 제거 가능합니다.
        try:
            from utils.config import Config
            Config.API_BASE_URL = self._api_base_url
        except ImportError:
            pass
