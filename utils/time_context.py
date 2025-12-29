"""
PlanCraft Agent - 시간 컨텍스트 유틸리티

LLM에게 현재 날짜/시간을 정확히 전달하기 위한 공통 모듈입니다.
네이버 타임 서버에서 정확한 시간을 가져와 사용합니다.
"""

from datetime import datetime
import requests

# 캐싱: 동일 실행 내에서 시간 서버 재호출 방지
_cached_time = None


def get_naver_time() -> datetime:
    """
    네이버 타임 서버에서 현재 시간을 가져옵니다.
    
    실패 시 로컬 시스템 시간을 반환합니다.
    
    Returns:
        datetime: 현재 시간
    """
    global _cached_time
    
    # 캐시된 시간이 있고, 10분 이내면 재사용
    if _cached_time:
        diff = (datetime.now() - _cached_time).total_seconds()
        if diff < 600:  # 10분
            return _cached_time
    
    try:
        # 네이버 메인 페이지에서 서버 시간 헤더 추출
        response = requests.head("https://www.naver.com", timeout=3)
        date_str = response.headers.get("Date")
        
        if date_str:
            # HTTP Date 형식: "Sun, 29 Dec 2025 05:20:00 GMT"
            from email.utils import parsedate_to_datetime
            server_time = parsedate_to_datetime(date_str)
            # GMT → KST 변환 (+9시간)
            from datetime import timedelta, timezone
            kst = timezone(timedelta(hours=9))
            _cached_time = server_time.astimezone(kst).replace(tzinfo=None)
            return _cached_time
    except Exception as e:
        print(f"[TIME] 네이버 타임 서버 조회 실패, 로컬 시간 사용: {e}")
    
    # Fallback: 로컬 시스템 시간
    return datetime.now()


def get_time_context() -> str:
    """
    현재 시간 컨텍스트를 반환합니다.
    
    모든 Agent 프롬프트에 주입하여 LLM이 정확한 날짜/시간을 인식하도록 합니다.
    
    Returns:
        str: 시간 컨텍스트 문자열 (시스템 프롬프트 상단에 추가)
    """
    now = get_naver_time()
    
    return f"""
=== 🕐 현재 시간 정보 (CRITICAL) ===
현재 날짜: {now.strftime("%Y년 %m월 %d일")}
현재 시간: {now.strftime("%H:%M:%S")}
현재 연도: {now.year}년
현재 분기: Q{(now.month - 1) // 3 + 1}

⚠️ 중요: 모든 일정, 로드맵, 타임라인은 위 날짜를 기준으로 작성하세요.
- "{now.year}년 {now.month + 1 if now.month < 12 else 1}월 출시" (O) 
- "2024년" 또는 과거 날짜 사용 금지 (X)
- 오늘 이후의 미래 날짜만 사용하세요.
=====================================

"""


def get_time_instruction() -> str:
    """
    시간 관련 명시적 지시를 반환합니다.
    
    User 프롬프트 끝에 추가하여 날짜 정확성을 강조합니다.
    """
    now = get_naver_time()
    
    return f"""

⏰ 날짜 확인: 오늘은 {now.year}년 {now.month}월 {now.day}일입니다.
예상 일정을 작성할 때 반드시 이 날짜 이후로 설정하세요.
"""


def get_current_year() -> int:
    """현재 연도 반환"""
    return get_naver_time().year


def get_current_date_str() -> str:
    """현재 날짜 문자열 반환 (YYYY-MM-DD)"""
    return get_naver_time().strftime("%Y-%m-%d")
