"""
PlanCraft - 로깅 설정 모듈

구조화된 JSON 로깅을 제공하여 운영 환경에서의 모니터링을 용이하게 합니다.
"""

import os
import sys
import logging
from typing import Optional

# JSON 로거 사용 가능 여부 확인
try:
    from pythonjsonlogger import jsonlogger
    JSON_LOGGER_AVAILABLE = True
except ImportError:
    JSON_LOGGER_AVAILABLE = False


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: Optional[str] = None
) -> None:
    """
    애플리케이션 로깅을 설정합니다.
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        json_format: JSON 포맷 사용 여부 (운영 환경 권장)
        log_file: 로그 파일 경로 (None이면 stdout만 사용)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 포맷터 설정
    if json_format and JSON_LOGGER_AVAILABLE:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
            json_ensure_ascii=False
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 파일 핸들러 (선택적)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # 외부 라이브러리 로그 레벨 조정 (너무 verbose 방지)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    
    root_logger.info(f"Logging initialized: level={level}, json={json_format and JSON_LOGGER_AVAILABLE}")


def get_logger(name: str) -> logging.Logger:
    """
    모듈별 로거를 반환합니다.
    
    Args:
        name: 로거 이름 (보통 __name__ 사용)
        
    Returns:
        logging.Logger: 설정된 로거
    """
    return logging.getLogger(name)


# 환경변수 기반 자동 설정
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
_LOG_JSON = os.getenv("LOG_JSON", "true").lower() == "true"
_LOG_FILE = os.getenv("LOG_FILE", None)

# 모듈 import 시 자동 설정 (선택적)
# setup_logging(level=_LOG_LEVEL, json_format=_LOG_JSON, log_file=_LOG_FILE)
