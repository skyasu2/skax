"""
Draft Validator Helper
"""
from typing import List
from graph.state import ensure_dict


def validate_draft(draft_dict: dict, preset, specialist_context: str,
                    refine_count: int, logger) -> List[str]:
    """
    생성된 초안 검증 (Self-Reflection)

    Args:
        draft_dict: 생성된 초안
        preset: 프리셋 설정
        specialist_context: 전문 에이전트 컨텍스트
        refine_count: 개선 횟수
        logger: 로거

    Returns:
        List[str]: 검증 실패 항목 목록 (빈 리스트면 통과)
    """
    sections = draft_dict.get("sections", [])
    section_count = len(sections)
    validation_issues = []

    MIN_SECTIONS = preset.min_sections
    MIN_CONTENT_LENGTH = 100

    # 검증 1: 섹션 개수
    if section_count < MIN_SECTIONS:
        validation_issues.append(f"섹션 개수 부족 ({section_count}/{MIN_SECTIONS}개)")

    # 검증 2: 섹션별 최소 길이
    short_sections = []
    for sec in sections:
        sec_dict = ensure_dict(sec)
        sec_name = sec_dict.get("name", "")
        sec_content = sec_dict.get("content", "")
        if len(sec_content) < MIN_CONTENT_LENGTH:
            short_sections.append(sec_name)

    if short_sections and len(short_sections) >= 3:
        validation_issues.append(f"부실 섹션 다수 ({', '.join(short_sections[:3])}...)")

    # 검증 3: Mermaid 다이어그램
    if preset.include_diagrams > 0:
        has_mermaid = any(
            "```mermaid" in ensure_dict(sec).get("content", "")
            for sec in sections
        )
        if not has_mermaid:
            validation_issues.append(f"Mermaid 다이어그램 누락")

    # 검증 4: ASCII 차트
    if preset.include_charts > 0:
        chart_indicators = ["▓", "░", "█", "■", "□", "●", "○"]
        has_chart = any(
            any(ind in ensure_dict(sec).get("content", "") for ind in chart_indicators)
            for sec in sections
        )
        if not has_chart:
            validation_issues.append(f"ASCII 차트 누락")

    # 검증 5: Specialist 분석 반영
    if specialist_context and refine_count == 0:
        all_content = " ".join(
            ensure_dict(sec).get("content", "")
            for sec in sections
        )
        specialist_checks = {
            "TAM/SAM/SOM": any(kw in all_content for kw in ["TAM", "SAM", "SOM", "시장 규모"]),
            "경쟁사 분석": any(kw in all_content for kw in ["경쟁사", "Competitor", "차별점"]),
            "BEP/손익분기": any(kw in all_content for kw in ["BEP", "손익분기", "손익 분기"]),
            "리스크": any(kw in all_content for kw in ["리스크", "Risk", "대응 방안", "위험"]),
        }
        missing = [k for k, v in specialist_checks.items() if not v]
        if missing:
            validation_issues.append(f"Specialist 데이터 누락: {', '.join(missing)}")

    return validation_issues
