import os
from pydantic import BaseModel, Field


# =============================================================================
# 생성 모드 프리셋 (Generation Presets)
# =============================================================================
#
# 사용자가 UI에서 선택하는 생성 모드에 따라 여러 파라미터를 동시에 조정합니다.
#
# ┌────────────┬─────────────┬────────────┬─────────────┬─────────────────────┐
# │ 모드       │ Temperature │ Max Refine │ Max Restart │ 특징                │
# ├────────────┼─────────────┼────────────┼─────────────┼─────────────────────┤
# │ ⚡ 빠른    │ 0.3         │ 1          │ 1           │ 속도 우선, 검토 최소│
# │ ⚖️ 균형   │ 0.7         │ 2          │ 2           │ 품질/속도 균형      │
# │ 💎 고품질 │ 1.0         │ 3          │ 2           │ 품질 우선, 검토 강화│
# └────────────┴─────────────┴────────────┴─────────────┴─────────────────────┘

class GenerationPreset(BaseModel):
    """생성 모드 프리셋 설정"""
    name: str = Field(description="프리셋 이름")
    icon: str = Field(description="UI 표시 아이콘")
    description: str = Field(description="프리셋 설명")
    temperature: float = Field(description="LLM 창의성 (0.0~1.0)")
    max_refine_loops: int = Field(description="최대 개선 루프 횟수")
    max_restart_count: int = Field(description="최대 재분석 횟수")
    writer_max_retries: int = Field(description="Writer 자체 검증 재시도")
    discussion_enabled: bool = Field(default=True, description="에이전트 토론 활성화")


# 프리셋 정의
GENERATION_PRESETS = {
    "fast": GenerationPreset(
        name="빠른 생성",
        icon="⚡",
        description="속도 우선, 빠른 결과물 생성",
        temperature=0.3,
        max_refine_loops=1,
        max_restart_count=1,
        writer_max_retries=1,
        discussion_enabled=False,
    ),
    "balanced": GenerationPreset(
        name="균형",
        icon="⚖️",
        description="품질과 속도의 균형 (권장)",
        temperature=0.7,
        max_refine_loops=2,
        max_restart_count=2,
        writer_max_retries=2,
        discussion_enabled=True,
    ),
    "quality": GenerationPreset(
        name="고품질",
        icon="💎",
        description="품질 우선, 철저한 검토",
        temperature=1.0,
        max_refine_loops=3,
        max_restart_count=2,
        writer_max_retries=3,
        discussion_enabled=True,
    ),
}

# 기본 프리셋
DEFAULT_PRESET = "balanced"


def get_preset(preset_key: str = None) -> GenerationPreset:
    """
    프리셋 설정 가져오기

    Args:
        preset_key: 프리셋 키 ("fast", "balanced", "quality")

    Returns:
        GenerationPreset: 해당 프리셋 설정

    Example:
        >>> preset = get_preset("quality")
        >>> print(preset.temperature)  # 1.0
    """
    key = preset_key or DEFAULT_PRESET
    return GENERATION_PRESETS.get(key, GENERATION_PRESETS[DEFAULT_PRESET])


# =============================================================================
# 프로젝트 전역 설정 (Project Settings)
# =============================================================================

class ProjectSettings(BaseModel):
    """
    PlanCraft 전역 설정 (Central Configuration)

    - 환경변수에서 로드하거나 기본값을 사용합니다.
    - 코드 내 하드코딩을 제거하고 이곳에서 통합 관리합니다.
    - 프리셋 기반 동적 설정을 지원합니다.
    """

    # === 현재 활성 프리셋 ===
    active_preset: str = Field(default=DEFAULT_PRESET, description="현재 활성화된 생성 모드")

    # === LLM Settings (기본값, 프리셋으로 오버라이드 가능) ===
    LLM_TEMPERATURE_CREATIVE: float = Field(default=0.7, description="창의적 생성 온도")
    LLM_TEMPERATURE_STRICT: float = Field(default=0.4, description="엄격한 생성 온도 (Writer 등)")
    LLM_TIMEOUT_SEC: int = Field(default=60, description="LLM 요청 타임아웃")

    # === Agent Settings ===
    MAX_FILE_LENGTH: int = Field(default=10000, description="업로드 파일 최대 분석 길이")
    WRITER_MAX_RETRIES: int = Field(default=3, description="Writer Self-Correction 최대 재시도 횟수")
    WRITER_MIN_SECTIONS: int = Field(default=9, description="Writer 최소 생성 섹션 수")

    # === Workflow Settings ===
    MAX_REFINE_LOOPS: int = Field(default=2, description="Refiner 최대 개선 루프 횟수")
    MIN_REMAINING_STEPS: int = Field(default=5, description="루프 종료 안전장치 (RecursionLimit 대비)")
    DISCUSSION_MAX_ROUNDS: int = Field(default=1, description="Reviewer-Writer 대화 최대 라운드")
    DISCUSSION_SKIP_THRESHOLD: int = Field(default=7, description="Discussion 건너뛰기 점수 (이상이면 스킵)")

    # === HITL (Human-in-the-Loop) Settings ===
    HITL_MAX_RETRIES: int = Field(default=5, description="사용자 입력 유효성 검사 최대 재시도 횟수")

    # === Analyzer Settings ===
    ANALYZER_FAST_TRACK_LENGTH: int = Field(default=20, description="Fast Track(바로 진행) 기준 입력 길이")

    # === UI Settings ===
    DEFAULT_THREAD_ID: str = Field(default="default_thread", description="기본 세션 ID")

    def get_effective_settings(self) -> dict:
        """
        현재 프리셋이 적용된 효과적인 설정값 반환

        프리셋 설정이 기본 설정을 오버라이드합니다.

        Returns:
            dict: 프리셋이 적용된 설정값
        """
        preset = get_preset(self.active_preset)
        return {
            "temperature": preset.temperature,
            "max_refine_loops": preset.max_refine_loops,
            "max_restart_count": preset.max_restart_count,
            "writer_max_retries": preset.writer_max_retries,
            "discussion_enabled": preset.discussion_enabled,
            # 기본 설정값들
            "writer_min_sections": self.WRITER_MIN_SECTIONS,
            "discussion_skip_threshold": self.DISCUSSION_SKIP_THRESHOLD,
            "hitl_max_retries": self.HITL_MAX_RETRIES,
        }

    @classmethod
    def load(cls) -> "ProjectSettings":
        """환경변수 오버라이드 지원 (Simple Factory)"""
        # Pydantic BaseSettings를 안 쓰는 대신 간단한 오버라이드 로직
        # 필요 시 os.getenv로 값 교체 가능
        return cls()


# 전역 설정 인스턴스 (Singleton)
settings = ProjectSettings.load()
