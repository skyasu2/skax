"""
UI Components - Mermaid 다이어그램 모듈

Mermaid 다이어그램 렌더링 관련 컴포넌트를 정의합니다.
"""

import re
import streamlit as st
import streamlit.components.v1 as components


def render_scalable_mermaid(mermaid_code: str, height: int = 300):
    """
    [NEW] Mermaid 다이어그램을 적절한 크기로 렌더링 (HTML/JS 활용)
    기본 st.markdown보다 크기 제어가 용이하며, Fit-to-screen을 지원합니다.
    """
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: true, theme: 'neutral' }});
        </script>
        <style>
            .mermaid-container {{
                display: flex;
                justify_content: center;
                align-items: center;
                width: 100%;
                height: 100%;
                overflow: hidden; 
            }}
            /* SVG 크기 자동 조절 (Fit to Container) */
            svg {{
                max-width: 100% !important;
                max-height: {height}px !important;
                height: auto !important;
            }}
        </style>
    </head>
    <body>
        <div class="mermaid-container">
            <div class="mermaid">
                {mermaid_code}
            </div>
        </div>
    </body>
    </html>
    """
    # iframe 높이를 조절하여 스크롤 없이 보이게 함
    components.html(html_code, height=height+20, scrolling=False)


def render_mermaid(code: str, height: int = 600, scale: float = 1.0, auto_fit: bool = False):
    """
    Mermaid 다이어그램 렌더링 (통합 버전)

    Args:
        code: Mermaid 다이어그램 코드
        height: 렌더링 높이 (기본 600px)
        scale: 확대 배율 (auto_fit=False일 때 적용)
        auto_fit: True일 경우 컨테이너 너비에 맞춤 (반응형)
    """
    if auto_fit:
        # 반응형 (Fit to Container) 스타일 - 오버랩 방지 및 가독성 개선
        css_style = f"""
        <style>
            .mermaid-container {{
                display: flex;
                justify_content: center;
                align-items: center;
                width: 100%;
                /* min-height를 주어 너무 납작해지는 것 방지 */
                min-height: {height // 2}px; 
            }}
            .mermaid {{
                width: 100%;
                text-align: center;
            }}
            /* SVG 크기 조절: 너비 100% 맞춤, 높이는 비율 유지하되 max-height 제한 */
            svg {{
                max-width: 100% !important;
                height: auto !important;
                max-height: {height}px !important;
            }}
        </style>
        """
        scrolling = False
    else:
        # 고정 스케일 (스크롤 가능) 스타일
        css_style = f"""
        <style>
            .mermaid-container {{
                overflow: auto;
                padding: 10px;
            }}
            .mermaid {{
                transform: scale({scale});
                transform-origin: top left;
            }}
            .mermaid svg {{
                max-width: none !important;
            }}
        </style>
        """
        scrolling = True

    components.html(
        f"""
        {css_style}
        <div class="mermaid-container">
            <div class="mermaid">
                {code}
            </div>
        </div>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{
                startOnLoad: true,
                securityLevel: 'loose',
                theme: 'base',
                themeVariables: {{
                    fontSize: '14px',
                    fontFamily: 'Pretendard, -apple-system, sans-serif',
                    primaryColor: '#e3f2fd',
                    primaryTextColor: '#1565c0',
                    primaryBorderColor: '#64b5f6',
                    lineColor: '#90caf9',
                    secondaryColor: '#f3e5f5',
                    tertiaryColor: '#fff'
                }},
                flowchart: {{
                    nodeSpacing: 50,
                    rankSpacing: 50,
                    padding: 15,
                    htmlLabels: true,
                    curve: 'basis'
                }},
                gantt: {{
                    fontSize: 11,
                    barHeight: 20,
                    barGap: 4,
                    topPadding: 50,
                    bottomPadding: 10,
                    leftPadding: 120,
                    rightPadding: 20,
                    gridLineStartPadding: 35,
                    sectionFontSize: 11,
                    numberSectionStyles: 4,
                    axisFormat: '%m월',
                    tickInterval: '1 month',
                    useMaxWidth: true
                }}
            }});
        </script>
        """,
        height=height,
        scrolling=scrolling
    )


def render_markdown_with_mermaid(content: str):
    """
    [NEW] Mermaid 다이어그램을 포함한 마크다운 렌더링

    마크다운 콘텐츠에서 ```mermaid 블록을 추출하여
    별도의 render_mermaid()로 시각화하고, 나머지는 st.markdown()으로 렌더링합니다.

    Args:
        content: 마크다운 문자열 (Mermaid 블록 포함 가능)
    """
    # Mermaid 블록 패턴: ```mermaid ... ```
    mermaid_pattern = r'```mermaid\s*([\s\S]*?)```'

    # 모든 Mermaid 블록 찾기
    mermaid_blocks = re.findall(mermaid_pattern, content)

    if not mermaid_blocks:
        # Mermaid 블록이 없으면 그냥 마크다운 렌더링
        st.markdown(content)
        return

    # Mermaid 블록을 플레이스홀더로 대체
    parts = re.split(mermaid_pattern, content)

    # parts 구조: [text_before, mermaid_code_1, text_between, mermaid_code_2, ...]
    # 짝수 인덱스: 일반 텍스트, 홀수 인덱스: Mermaid 코드
    for i, part in enumerate(parts):
        if not part.strip():
            continue

        if i % 2 == 0:
            # 일반 마크다운 텍스트
            st.markdown(part)
        else:
            # Mermaid 코드 블록 - 시각적 렌더링 (반응형 fit)
            st.markdown("---")
            st.caption("📊 Mermaid 다이어그램")
            # auto_fit=True로 설정하여 화면에 맞게 렌더링
            render_mermaid(part.strip(), height=500, auto_fit=True)
            st.markdown("---")
