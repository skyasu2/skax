import os
from pydantic import BaseModel, Field


# =============================================================================
# 생성 모드 프리셋 (Generation Presets)
# =============================================================================
#
# 사용자가 UI에서 선택하는 생성 모드에 따라 여러 파라미터를 동시에 조정합니다.
#
# ┌────────────┬─────────────┬────────────┬─────────────┬────────────┬───────────────┬─────────────────────┐
# │ 모드       │ Temperature │ Max Refine │ Struct검증  │ Writer검증 │ 최소 섹션     │ 특징                │
# ├────────────┼─────────────┼────────────┼─────────────┼────────────┼───────────────┼─────────────────────┤
# │ ⚡ 빠른    │ 0.3         │ 1          │ 2 (고정)    │ 1          │ 7개           │ 속도 우선           │
# │ ⚖️ 균형   │ 0.7         │ 2          │ 2 (고정)    │ 2          │ 9개           │ 품질/속도 균형      │
# │ 💎 고품질 │ 1.0         │ 3          │ 2 (고정)    │ 3          │ 10개          │ 품질 우선           │
# └────────────┴─────────────┴────────────┴─────────────┴────────────┴───────────────┴─────────────────────┘

class GenerationPreset(BaseModel):
    """생성 모드 프리셋 설정"""
    name: str = Field(description="프리셋 이름")
    icon: str = Field(description="UI 표시 아이콘")
    description: str = Field(description="프리셋 설명")
    model_type: str = Field(default="gpt-4o", description="사용할 LLM 모델 타입")  # [NEW] 모델 타입 추가
    temperature: float = Field(description="LLM 창의성 (0.0~1.0)")
    max_refine_loops: int = Field(description="최대 개선 루프 횟수")
    max_restart_count: int = Field(description="최대 재분석 횟수")
    writer_max_retries: int = Field(description="Writer 자체 검증 재시도")
    discussion_enabled: bool = Field(default=True, description="에이전트 토론 활성화")
    # [NEW] 방안 D: 핵심 검증 보장
    min_sections: int = Field(default=9, description="최소 생성 섹션 수")
    structurer_max_retries: int = Field(default=2, description="Structurer 검증 재시도 (고정)")
    # [NEW] 시각적 요소 설정 (다이어그램, 그래프)
    include_diagrams: int = Field(default=0, description="포함할 Mermaid 다이어그램 개수")
    include_charts: int = Field(default=0, description="포함할 Markdown 그래프/차트 개수")


# 프리셋 정의
# [FIX] balanced를 첫 번째로 배치하여 Streamlit selectbox 기본값 보장
# - Streamlit의 key 파라미터 사용 시 session_state 타이밍 이슈로 첫 번째 옵션이 선택될 수 있음
# - 딕셔너리 순서: balanced(권장) → fast → quality
GENERATION_PRESETS = {
    "balanced": GenerationPreset(
        name="균형",
        icon="⚖️",
        description="품질과 속도의 균형 (권장)",
        model_type="gpt-4o",  # 균형: GPT-4o 사용
        temperature=0.7,
        max_refine_loops=2,
        max_restart_count=2,
        writer_max_retries=2,
        discussion_enabled=True,
        min_sections=9,  # 균형: 9개 섹션
        structurer_max_retries=2,  # 구조 검증은 고정
        include_diagrams=1,  # 균형 모드: 다이어그램 1개
        include_charts=1,    # 그래프 1개
    ),
    "fast": GenerationPreset(
        name="빠른 생성",
        icon="⚡",
        description="속도 우선, 빠른 결과물 생성",
        model_type="gpt-4o-mini",  # [IMPROVE] 빠른 생성: GPT-4o-mini 사용 (속도/비용 최적화)
        temperature=0.3,
        max_refine_loops=1,
        max_restart_count=1,
        writer_max_retries=1,
        discussion_enabled=False,
        min_sections=7,  # 속도 우선: 7개 섹션
        structurer_max_retries=2,  # 구조 검증은 고정
        include_diagrams=0,  # 빠른 모드: 시각 자료 없음
        include_charts=0,
    ),
    "quality": GenerationPreset(
        name="고품질",
        icon="💎",
        description="품질 우선, 철저한 검토",
        model_type="gpt-4o",  # 고품질: GPT-4o 필수
        temperature=0.8,  # [IMPROVE] 1.0 -> 0.8 (안정성 확보)
        max_refine_loops=3,
        max_restart_count=2,
        writer_max_retries=3,
        discussion_enabled=True,
        min_sections=10,  # 고품질: 10개 섹션
        structurer_max_retries=2,  # 구조 검증은 고정
        include_diagrams=1,  # 고품질 모드: 다이어그램 1개
        include_charts=2,    # 그래프 2개 (추가 1개)
    ),
}

# 기본 프리셋
DEFAULT_PRESET = "balanced"


# =============================================================================
# 품질 점수 임계값 (Quality Thresholds)
# =============================================================================
# 매직 넘버를 중앙화하여 코드 전반에서 일관되게 사용합니다.

class QualityThresholds:
    """
    품질 평가 점수 임계값

    워크플로우 라우팅에서 사용되는 점수 기준을 중앙 관리합니다.
    """
    # 리뷰어 판정 기준
    SCORE_PASS = 9          # 이상이면 PASS (바로 포맷팅)
    SCORE_FAIL = 5          # 미만이면 FAIL (재분석)
    SCORE_REVISE_MIN = 5    # 5~8점: REVISE (개선 필요)
    SCORE_REVISE_MAX = 8

    # 토론 스킵 기준 (DISCUSSION_SKIP)
    DISCUSSION_SKIP = 9     # 9점 이상이면 토론 없이 바로 개선

    # 재시작 제한
    MAX_RESTART_COUNT = 2   # 최대 재분석 횟수
    MAX_REFINE_LOOPS = 3    # 최대 개선 루프

    # Fallback 점수 (리뷰어 오류 시)
    FALLBACK_SCORE = 7      # 리뷰어 실패 시 기본 점수

    @classmethod
    def is_pass(cls, score: int) -> bool:
        """점수가 통과 기준인지 확인"""
        return score >= cls.SCORE_PASS

    @classmethod
    def is_fail(cls, score: int) -> bool:
        """점수가 실패 기준인지 확인"""
        return score < cls.SCORE_FAIL

    @classmethod
    def is_revise(cls, score: int) -> bool:
        """점수가 개선 필요 범위인지 확인"""
        return cls.SCORE_REVISE_MIN <= score <= cls.SCORE_REVISE_MAX

    @classmethod
    def should_skip_discussion(cls, score: int) -> bool:
        """토론을 건너뛰어도 되는 점수인지 확인"""
        return score >= cls.DISCUSSION_SKIP


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
    
    # [NEW] 점수 임계값 (매직 넘버 제거)
    SCORE_THRESHOLD_PASS: int = Field(default=9, description="통과 기준 점수 (이상)")
    SCORE_THRESHOLD_FAIL: int = Field(default=5, description="실패 기준 점수 (미만)")
    
    DISCUSSION_MAX_ROUNDS: int = Field(default=2, description="Reviewer-Writer 대화 최대 라운드 (데모 효과 강화)")
    DISCUSSION_SKIP_THRESHOLD: int = Field(default=9, description="Discussion 건너뛰기 점수 (9점 미만은 무조건 토론)")

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
            "model_type": preset.model_type,  # [NEW] 모델 타입 전달
            "temperature": preset.temperature,
            "max_refine_loops": preset.max_refine_loops,
            "max_restart_count": preset.max_restart_count,
            "writer_max_retries": preset.writer_max_retries,
            "discussion_enabled": preset.discussion_enabled,
            # [NEW] 프리셋 기반 섹션 수 및 검증 설정
            "min_sections": preset.min_sections,
            "structurer_max_retries": preset.structurer_max_retries,
            # 기본 설정값들
            "discussion_skip_threshold": self.DISCUSSION_SKIP_THRESHOLD,
            "hitl_max_retries": self.HITL_MAX_RETRIES,
        }

    @classmethod
    def load(cls) -> "ProjectSettings":
        """
        환경변수 오버라이드 지원 (Simple Factory)

        지원 환경변수:
        - PLANCRAFT_PRESET: 기본 프리셋 (fast/balanced/quality)
        - PLANCRAFT_LLM_TIMEOUT: LLM 타임아웃 (초)
        - PLANCRAFT_MAX_REFINE: 최대 개선 루프
        - PLANCRAFT_DISCUSSION_ROUNDS: 토론 최대 라운드
        """
        overrides = {}

        # 프리셋 오버라이드
        if preset := os.getenv("PLANCRAFT_PRESET"):
            if preset in GENERATION_PRESETS:
                overrides["active_preset"] = preset

        # LLM 타임아웃
        if timeout := os.getenv("PLANCRAFT_LLM_TIMEOUT"):
            try:
                overrides["LLM_TIMEOUT_SEC"] = int(timeout)
            except ValueError:
                pass

        # 최대 개선 루프
        if max_refine := os.getenv("PLANCRAFT_MAX_REFINE"):
            try:
                overrides["MAX_REFINE_LOOPS"] = int(max_refine)
            except ValueError:
                pass

        # 토론 최대 라운드
        if disc_rounds := os.getenv("PLANCRAFT_DISCUSSION_ROUNDS"):
            try:
                overrides["DISCUSSION_MAX_ROUNDS"] = int(disc_rounds)
            except ValueError:
                pass

        return cls(**overrides)


# 전역 설정 인스턴스 (Singleton)
settings = ProjectSettings.load()
