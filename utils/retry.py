"""
PlanCraft - LLM Retry 유틸리티

LangChain LLM 호출에 대한 Exponential Backoff with Jitter를 제공합니다.

Best Practice 기반:
    - LangChain RunnableRetry (with_retry 메서드)
    - Tenacity 라이브러리 패턴
    - 2025 LangChain 공식 권장사항

핵심 원칙:
    1. Retriable vs Non-Retriable 에러 명확 분류
    2. Exponential Backoff with Jitter (Thundering Herd 방지)
    3. 최소 범위 Retry (전체 체인이 아닌 LLM 호출만)
    4. 최대 재시도 횟수 제한 (기본 3회)

사용 예시:
    from utils.retry import get_llm_with_retry, RETRIABLE_EXCEPTIONS

    # 방법 1: 래핑된 LLM 사용
    llm = get_llm_with_retry(temperature=0.7)
    response = llm.invoke(messages)

    # 방법 2: 기존 LLM에 retry 적용
    from utils.retry import apply_retry
    llm_with_retry = apply_retry(existing_llm)

참조:
    - https://docs.langchain.com/langsmith/rate-limiting
    - https://api.python.langchain.com/en/latest/runnables/langchain_core.runnables.retry.RunnableRetry.html
"""

import random
import time
import functools
from typing import Type, Tuple, Callable, Any, Optional
from dataclasses import dataclass

# =============================================================================
# Retriable Exception 분류
# =============================================================================

# LLM API 호출 시 재시도 가능한 예외 목록
# - 5xx 서버 에러
# - 429 Too Many Requests (Rate Limit)
# - 네트워크 일시적 오류
RETRIABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    # OpenAI/Azure 관련
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    # 일반 네트워크 오류
    OSError,  # includes socket errors
)

# 재시도하면 안 되는 예외 (즉시 실패 처리)
# - 4xx 클라이언트 에러 (429 제외)
# - 인증 오류
# - 잘못된 요청
NON_RETRIABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


def is_retriable_error(exception: Exception) -> bool:
    """
    예외가 재시도 가능한지 판단합니다.

    Args:
        exception: 발생한 예외

    Returns:
        bool: 재시도 가능 여부

    판단 기준:
        1. RETRIABLE_EXCEPTIONS 타입 체크
        2. 에러 메시지에 retriable 키워드 포함 여부
        3. HTTP 상태 코드 확인 (429, 5xx)
    """
    # 명시적으로 재시도 불가한 예외
    if isinstance(exception, NON_RETRIABLE_EXCEPTIONS):
        return False

    # 명시적으로 재시도 가능한 예외
    if isinstance(exception, RETRIABLE_EXCEPTIONS):
        return True

    # 에러 메시지 기반 판단
    error_msg = str(exception).lower()

    # Rate Limit 관련
    rate_limit_keywords = ["rate limit", "too many requests", "429", "quota"]
    if any(kw in error_msg for kw in rate_limit_keywords):
        return True

    # 서버 에러 (5xx)
    server_error_keywords = ["500", "502", "503", "504", "server error", "internal error"]
    if any(kw in error_msg for kw in server_error_keywords):
        return True

    # 일시적 네트워크 오류
    network_keywords = ["timeout", "connection", "network", "temporarily"]
    if any(kw in error_msg for kw in network_keywords):
        return True

    # 기본값: 재시도 안함 (안전한 기본값)
    return False


# =============================================================================
# Retry 설정
# =============================================================================

@dataclass
class RetryConfig:
    """
    Retry 동작 설정

    Attributes:
        max_attempts: 최대 재시도 횟수 (기본 3)
        initial_wait: 첫 재시도 전 대기 시간 (초, 기본 1.0)
        max_wait: 최대 대기 시간 (초, 기본 60.0)
        exponential_base: 지수 백오프 배수 (기본 2.0)
        jitter: Jitter 활성화 여부 (기본 True)
        jitter_range: Jitter 범위 (0.0 ~ 1.0, 기본 0.5)
    """
    max_attempts: int = 3
    initial_wait: float = 1.0
    max_wait: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.5


# 기본 설정 (프로덕션 권장값)
DEFAULT_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_wait=1.0,
    max_wait=60.0,
    exponential_base=2.0,
    jitter=True,
    jitter_range=0.5,
)

# Rate Limit 전용 설정 (더 긴 대기 시간)
RATE_LIMIT_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    initial_wait=5.0,
    max_wait=120.0,
    exponential_base=2.0,
    jitter=True,
    jitter_range=0.3,
)


# =============================================================================
# Exponential Backoff with Jitter 계산
# =============================================================================

def calculate_backoff_wait(
    attempt: int,
    config: RetryConfig = DEFAULT_RETRY_CONFIG
) -> float:
    """
    Exponential Backoff with Jitter 대기 시간 계산

    Args:
        attempt: 현재 재시도 횟수 (0-based)
        config: Retry 설정

    Returns:
        float: 대기 시간 (초)

    Algorithm:
        base_wait = initial_wait * (exponential_base ^ attempt)
        if jitter:
            jitter_amount = base_wait * random(-jitter_range, +jitter_range)
            wait = base_wait + jitter_amount
        return min(wait, max_wait)

    Example:
        attempt 0: 1.0s (± jitter)
        attempt 1: 2.0s (± jitter)
        attempt 2: 4.0s (± jitter)
    """
    # 지수 백오프 기본값
    base_wait = config.initial_wait * (config.exponential_base ** attempt)

    # Jitter 적용 (Thundering Herd 방지)
    if config.jitter:
        jitter_factor = 1.0 + random.uniform(-config.jitter_range, config.jitter_range)
        wait = base_wait * jitter_factor
    else:
        wait = base_wait

    # 최대 대기 시간 제한
    return min(wait, config.max_wait)


# =============================================================================
# Retry Decorator
# =============================================================================

def with_retry(
    config: RetryConfig = DEFAULT_RETRY_CONFIG,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
):
    """
    Exponential Backoff with Jitter를 적용하는 데코레이터

    Args:
        config: Retry 설정
        on_retry: 재시도 시 호출되는 콜백 (attempt, exception, wait_time)

    Returns:
        데코레이터 함수

    Example:
        @with_retry(config=DEFAULT_RETRY_CONFIG)
        def call_llm(prompt: str) -> str:
            return llm.invoke(prompt)

        # 콜백과 함께 사용
        def log_retry(attempt, exc, wait):
            print(f"Retry {attempt}: {exc}, waiting {wait:.2f}s")

        @with_retry(on_retry=log_retry)
        def call_llm(prompt: str) -> str:
            return llm.invoke(prompt)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # 재시도 가능 여부 확인
                    if not is_retriable_error(e):
                        raise

                    # 마지막 시도인 경우 재시도 없이 예외 발생
                    if attempt >= config.max_attempts - 1:
                        raise

                    # 대기 시간 계산
                    wait_time = calculate_backoff_wait(attempt, config)

                    # 콜백 호출
                    if on_retry:
                        on_retry(attempt + 1, e, wait_time)
                    else:
                        # 기본 로깅
                        print(
                            f"[Retry] Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                            f"Retrying in {wait_time:.2f}s..."
                        )

                    # 대기
                    time.sleep(wait_time)

            # 모든 재시도 실패 (이론상 도달하지 않음)
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


# =============================================================================
# LangChain LLM에 Retry 적용
# =============================================================================

def apply_retry_to_llm(
    llm,
    config: RetryConfig = DEFAULT_RETRY_CONFIG
):
    """
    기존 LangChain LLM에 with_retry() 적용

    LangChain의 공식 with_retry() 메서드를 사용합니다.
    이 방법은 RunnableRetry를 활용하여 LLM 호출만 retry합니다.

    Args:
        llm: LangChain BaseChatModel 인스턴스
        config: Retry 설정

    Returns:
        RunnableRetry: Retry가 적용된 LLM

    Example:
        from utils.llm import get_llm
        from utils.retry import apply_retry_to_llm

        llm = get_llm(temperature=0.7)
        llm_with_retry = apply_retry_to_llm(llm)
        response = llm_with_retry.invoke(messages)
    """
    return llm.with_retry(
        retry_if_exception_type=RETRIABLE_EXCEPTIONS,
        wait_exponential_jitter=config.jitter,
        stop_after_attempt=config.max_attempts,
    )


def get_llm_with_retry(
    model_type: str = "gpt-4o",
    temperature: float = 0.7,
    retry_config: RetryConfig = DEFAULT_RETRY_CONFIG
):
    """
    Retry가 적용된 LLM 인스턴스 반환

    Args:
        model_type: 모델 타입 (gpt-4o, gpt-4o-mini)
        temperature: 생성 온도
        retry_config: Retry 설정

    Returns:
        RunnableRetry: Retry가 적용된 LLM

    Example:
        from utils.retry import get_llm_with_retry

        llm = get_llm_with_retry(temperature=0.3)
        response = llm.invoke(messages)
    """
    from utils.llm import get_llm

    base_llm = get_llm(model_type=model_type, temperature=temperature)
    return apply_retry_to_llm(base_llm, retry_config)


# =============================================================================
# Structured Output용 Retry 래퍼
# =============================================================================

def get_structured_llm_with_retry(
    schema,
    model_type: str = "gpt-4o",
    temperature: float = 0.7,
    retry_config: RetryConfig = DEFAULT_RETRY_CONFIG
):
    """
    Retry가 적용된 Structured Output LLM 반환

    with_structured_output() 호출 전에 retry를 적용하여
    Pydantic 검증 실패는 재시도하지 않고, API 오류만 재시도합니다.

    Args:
        schema: Pydantic 모델 또는 JSON Schema
        model_type: 모델 타입
        temperature: 생성 온도
        retry_config: Retry 설정

    Returns:
        Structured Output이 적용된 LLM (with retry)

    Example:
        from utils.retry import get_structured_llm_with_retry
        from utils.schemas import AnalysisResult

        llm = get_structured_llm_with_retry(
            schema=AnalysisResult,
            temperature=0.7
        )
        result = llm.invoke(messages)  # AnalysisResult 타입 반환
    """
    llm_with_retry = get_llm_with_retry(
        model_type=model_type,
        temperature=temperature,
        retry_config=retry_config
    )

    return llm_with_retry.with_structured_output(schema)


# =============================================================================
# 로깅 통합
# =============================================================================

def create_retry_logger():
    """
    FileLogger와 통합된 retry 콜백 생성

    Returns:
        Callable: on_retry 콜백 함수

    Example:
        @with_retry(on_retry=create_retry_logger())
        def call_api():
            ...
    """
    def log_retry(attempt: int, exception: Exception, wait_time: float):
        try:
            from utils.file_logger import get_file_logger
            logger = get_file_logger()
            logger.warning(
                f"[LLM_RETRY] Attempt {attempt} failed: {type(exception).__name__}: {str(exception)[:100]}. "
                f"Waiting {wait_time:.2f}s before retry..."
            )
        except ImportError:
            print(f"[Retry] Attempt {attempt}: {exception}, waiting {wait_time:.2f}s")

    return log_retry


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # 설정
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",
    "RATE_LIMIT_RETRY_CONFIG",

    # 예외 분류
    "RETRIABLE_EXCEPTIONS",
    "NON_RETRIABLE_EXCEPTIONS",
    "is_retriable_error",

    # 핵심 함수
    "calculate_backoff_wait",
    "with_retry",

    # LLM 통합
    "apply_retry_to_llm",
    "get_llm_with_retry",
    "get_structured_llm_with_retry",

    # 로깅
    "create_retry_logger",
]
