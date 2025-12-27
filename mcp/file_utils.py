"""
PlanCraft Agent - 파일 유틸리티 모듈

기획서 파일 저장 및 관리를 위한 간단한 유틸리티입니다.
기존 filesystem MCP를 대체하는 경량 구현입니다.

사용 예시:
    from mcp.file_utils import save_plan, list_saved_plans

    # 기획서 저장
    path = save_plan("# 기획서 내용")

    # 저장된 목록 조회
    files = list_saved_plans()
"""

import os
from datetime import datetime
from typing import List, Optional


# 기본 출력 디렉토리
OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")


def save_plan(content: str, filename: Optional[str] = None) -> str:
    """
    기획서를 파일로 저장합니다.

    Args:
        content: 저장할 기획서 내용 (마크다운)
        filename: 파일명 (없으면 자동 생성)

    Returns:
        str: 저장된 파일의 전체 경로

    Example:
        >>> path = save_plan("# 점심 메뉴 추천 앱 기획서")
        >>> print(f"저장됨: {path}")
    """
    # outputs 폴더 생성
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    # 파일명 생성
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"기획서_{timestamp}.md"

    # 저장
    file_path = os.path.join(OUTPUTS_DIR, filename)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return file_path


def list_saved_plans(limit: int = 10) -> List[str]:
    """
    저장된 기획서 목록을 반환합니다.

    Args:
        limit: 반환할 최대 파일 수

    Returns:
        List[str]: 파일 경로 목록 (최신순)

    Example:
        >>> files = list_saved_plans(5)
        >>> for f in files:
        ...     print(os.path.basename(f))
    """
    if not os.path.exists(OUTPUTS_DIR):
        return []

    files = []
    for f in os.listdir(OUTPUTS_DIR):
        if f.endswith('.md'):
            full_path = os.path.join(OUTPUTS_DIR, f)
            if os.path.isfile(full_path):
                files.append(full_path)

    # 수정 시간 기준 정렬 (최신순)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    return files[:limit]


def read_plan(file_path: str) -> str:
    """
    저장된 기획서를 읽습니다.

    Args:
        file_path: 파일 경로

    Returns:
        str: 파일 내용

    Raises:
        FileNotFoundError: 파일이 없을 때
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()
