import os
from pydantic import BaseModel, Field

class ProjectSettings(BaseModel):
    """
    PlanCraft 전역 설정 (Central Configuration)
    - 환경변수에서 로드하거나 기본값을 사용합니다.
    - 코드 내 하드코딩을 제거하고 이곳에서 통합 관리합니다.
    """
    
    # === LLM Settings ===
    LLM_TEMPERATURE_CREATIVE: float = Field(default=0.7, description="창의적 생성 온도")
    LLM_TEMPERATURE_STRICT: float = Field(default=0.4, description="엄격한 생성 온도 (Writer 등)")
    LLM_TIMEOUT_SEC: int = Field(default=60, description="LLM 요청 타임아웃")
    
    # === Agent Settings ===
    MAX_FILE_LENGTH: int = Field(default=10000, description="업로드 파일 최대 분석 길이")
    WRITER_MAX_RETRIES: int = Field(default=3, description="Writer Self-Correction 최대 재시도 횟수")
    WRITER_MIN_SECTIONS: int = Field(default=9, description="Writer 최소 생성 섹션 수")
    
    # === Workflow Settings ===
    MAX_REFINE_LOOPS: int = Field(default=3, description="Refiner 최대 개선 루프 횟수")
    MIN_REMAINING_STEPS: int = Field(default=5, description="루프 종료 안전장치 (RecursionLimit 대비)")
    DISCUSSION_MAX_ROUNDS: int = Field(default=3, description="Reviewer-Writer 대화 최대 라운드")

    # === HITL (Human-in-the-Loop) Settings ===
    HITL_MAX_RETRIES: int = Field(default=5, description="사용자 입력 유효성 검사 최대 재시도 횟수")

    # === Analyzer Settings ===
    ANALYZER_FAST_TRACK_LENGTH: int = Field(default=20, description="Fast Track(바로 진행) 기준 입력 길이")
    
    # === UI Settings ===
    DEFAULT_THREAD_ID: str = Field(default="default_thread", description="기본 세션 ID")

    @classmethod
    def load(cls) -> "ProjectSettings":
        """환경변수 오버라이드 지원 (Simple Factory)"""
        # Pydantic BaseSettings를 안 쓰는 대신 간단한 오버라이드 로직
        # 필요 시 os.getenv로 값 교체 가능
        return cls()

# 전역 설정 인스턴스 (Singleton)
settings = ProjectSettings.load()
