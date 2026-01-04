"""
Prompt Builder Helper
"""
from utils.file_logger import get_file_logger
from graph.state import ensure_dict, PlanCraftState
from prompts.writer_prompt import WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT
from prompts.business_plan_prompt import BUSINESS_PLAN_SYSTEM_PROMPT, BUSINESS_PLAN_USER_PROMPT

def get_prompts_by_doc_type(state: PlanCraftState) -> tuple:
    """
    doc_type에 따라 적절한 프롬프트 반환

    Args:
        state: 현재 워크플로우 상태

    Returns:
        Tuple[str, str]: (system_prompt, user_prompt_template)
    """
    logger = get_file_logger()
    analysis = state.get("analysis")
    analysis_dict = ensure_dict(analysis)
    doc_type = analysis_dict.get("doc_type", "web_app_plan")

    if doc_type == "business_plan":
        logger.info("[Writer] 비IT 사업 기획서 모드로 작성합니다.")
        return BUSINESS_PLAN_SYSTEM_PROMPT, BUSINESS_PLAN_USER_PROMPT
    else:
        logger.info("[Writer] IT/Tech 기획서 모드로 작성합니다.")
        return WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT


def build_review_context(state: PlanCraftState, refine_count: int) -> str:
    """
    Reviewer 피드백을 컨텍스트 문자열로 변환

    Args:
        state: 현재 상태
        refine_count: 개선 횟수

    Returns:
        str: 리뷰 피드백 메시지 (없으면 빈 문자열)
    """
    if refine_count == 0:
        return ""

    review_data = state.get("review")
    if not review_data:
        return ""

    review_dict = ensure_dict(review_data)
    verdict = review_dict.get("verdict", "")
    feedback_summary = review_dict.get("feedback_summary", "")
    critical_issues = review_dict.get("critical_issues", [])
    action_items = review_dict.get("action_items", [])

    return f"""
=====================================================================
🚨 [REVISION REQUIRED] 이전 버전에 대한 심사 피드백 (반드시 반영할 것) 🚨
판정: {verdict}
지적 사항: {feedback_summary}
치명적 문제: {', '.join(critical_issues) if critical_issues else '없음'}
Action Items (실행 지침):
{chr(10).join([f'- {item}' for item in action_items])}
=====================================================================
"""


def build_refinement_context(refine_count: int, min_sections: int) -> str:
    """
    개선 모드용 컨텍스트 생성

    Args:
        refine_count: 현재 개선 횟수
        min_sections: 최소 섹션 수

    Returns:
        str: 개선 모드 지침 메시지
    """
    if refine_count == 0:
        return ""

    return f"""
=====================================================================
🔄 [REFINEMENT MODE] 개선 라운드 {refine_count} - 완전히 새로 작성하세요!
=====================================================================

⚠️ 이번은 {refine_count}번째 개선 시도입니다.
⚠️ 이전 버전의 피드백을 반영하여 **처음부터 완전히 새로 작성**하세요.
⚠️ 이전 버전을 참조하지 마세요. 아래 structure를 따라 **모든 {min_sections}개 섹션**을 작성하세요!

🎯 필수 요구사항:
1. sections 배열에 **정확히 {min_sections}개 이상**의 섹션 포함
2. 각 섹션은 **최소 300자 이상** 상세하게 작성
3. structure에 정의된 **모든 섹션**을 빠짐없이 작성
4. 부분 출력 절대 금지 - 완전한 기획서 출력 필수

=====================================================================
"""


def build_visual_instruction(preset, logger) -> str:
    """
    프리셋 기반 시각적 요소 지침 생성

    Args:
        preset: 생성 프리셋 설정
        logger: 로거 인스턴스

    Returns:
        str: 시각화 지침 문자열
    """
    if preset.include_diagrams == 0 and preset.include_charts == 0:
        return ""

    visual_instruction = """

=====================================================================
📊 **[필수] 시각적 요소 요구사항** - 반드시 포함할 것!
=====================================================================
"""

    if preset.include_diagrams > 0:
        # Mermaid 커스텀 옵션 적용
        diagram_types = getattr(preset, 'diagram_types', ['flowchart', 'sequenceDiagram'])
        direction = getattr(preset, 'diagram_direction', 'TB')
        theme = getattr(preset, 'diagram_theme', 'default')

        # 다이어그램 유형별 예시 생성
        type_examples = {
            "flowchart": f"""```mermaid
%%{{init: {{'theme': '{theme}'}}}}%%
flowchart {direction}
    A[사용자 접속] --> B[로그인/회원가입]
    B --> C{{서비스 선택}}
    C -->|기능A| D[기능A 처리]
    C -->|기능B| E[기능B 처리]
    D --> F[결과 표시]
    E --> F
```""",
            "sequenceDiagram": f"""```mermaid
%%{{init: {{'theme': '{theme}'}}}}%%
sequenceDiagram
    actor User as 사용자
    participant API as 백엔드
    participant DB as 데이터베이스
    User->>API: 요청 전송
    API->>DB: 데이터 조회
    DB-->>API: 결과 반환
    API-->>User: 응답 표시
```""",
            "classDiagram": f"""```mermaid
%%{{init: {{'theme': '{theme}'}}}}%%
classDiagram
    class User {{
        +String name
        +login()
    }}
    class Service {{
        +process()
    }}
    User --> Service
```""",
            "erDiagram": f"""```mermaid
%%{{init: {{'theme': '{theme}'}}}}%%
erDiagram
    USER ||--o{{ ORDER : places
    ORDER ||--|{{ ITEM : contains
```""",
        }

        # 선호 다이어그램 유형에서 첫 번째 예시 선택
        primary_type = diagram_types[0] if diagram_types else "flowchart"
        example_diagram = type_examples.get(primary_type, type_examples["flowchart"])

        visual_instruction += f"""
### Mermaid 다이어그램 ({preset.include_diagrams}개 이상 필수)
**권장 삽입 위치**: "시스템 아키텍처", "사용자 플로우", 또는 "서비스 구조" 섹션
**선호 다이어그램 유형**: {', '.join(diagram_types)}
**방향**: {direction} | **테마**: {theme}

아래 형식을 **정확히** 사용하세요 (백틱 3개 + mermaid):
{example_diagram}
"""

    if preset.include_charts > 0:
        visual_instruction += f"""
### ASCII 막대 그래프 ({preset.include_charts}개 이상 필수)
**권장 삽입 위치**: "수익 모델", "성장 전략", 또는 "마일스톤" 섹션

아래 형식을 사용하세요 (▓와 ░ 문자 사용):
| 구분 | 수치 | 그래프 |
|------|-----:|--------|
| 1분기 | 1,000명 | ▓▓░░░░░░░░ 20% |
| 2분기 | 2,500명 | ▓▓▓▓▓░░░░░ 50% |
| 3분기 | 4,000명 | ▓▓▓▓▓▓▓▓░░ 80% |
| 4분기 | 5,000명 | ▓▓▓▓▓▓▓▓▓▓ 100% |
"""

    visual_instruction += """
🚨 **경고**: 위 시각적 요소가 포함되지 않으면 검증 실패로 재작성 요청됩니다!
=====================================================================
"""
    logger.info(f"[Writer] 시각적 요소 요청: 다이어그램 {preset.include_diagrams}개, 차트 {preset.include_charts}개")

    return visual_instruction


def build_visual_feedback(validation_issues: list, preset) -> str:
    """
    시각적 요소 누락 시 구체적인 생성 예시가 포함된 피드백 생성

    Args:
        validation_issues: 검증 실패 항목 목록
        preset: 프리셋 설정

    Returns:
        str: 구체적인 시각적 요소 생성 지침
    """
    feedback_parts = []

    if "Mermaid 다이어그램 누락" in validation_issues:
        feedback_parts.append("""
⚠️ **Mermaid 다이어그램 필수**: 아래 형식으로 섹션에 포함하세요!
```mermaid
graph TB
    A[사용자 요청] --> B[서비스 처리]
    B --> C{결과 확인}
    C -->|성공| D[응답 반환]
    C -->|실패| E[에러 처리]
```
다이어그램을 '시스템 아키텍처' 또는 '사용자 플로우' 섹션에 추가하세요.
""")

    if "ASCII 차트 누락" in validation_issues:
        feedback_parts.append("""
⚠️ **ASCII 차트 필수**: 아래 형식으로 섹션에 포함하세요!
| 구분 | 수치 | 그래프 |
|------|-----:|--------|
| 1분기 | 1,000 | ▓▓░░░░░░░░ 20% |
| 2분기 | 2,500 | ▓▓▓▓▓░░░░░ 50% |
| 3분기 | 4,000 | ▓▓▓▓▓▓▓▓░░ 80% |
| 4분기 | 5,000 | ▓▓▓▓▓▓▓▓▓▓ 100% |
차트를 '수익 모델' 또는 '성장 전략' 섹션에 추가하세요.
""")

    return "\n".join(feedback_parts) if feedback_parts else ""
