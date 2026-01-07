"""
Formatter Node
"""
from agents.formatter import run as formatter_run
from graph.state import PlanCraftState, update_state
from graph.nodes.common import update_step_history
from utils.tracing import trace_node
from utils.error_handler import handle_node_error
import re
from urllib.parse import urlparse

@trace_node("format", tags=["output", "final"])
@handle_node_error
def run_formatter_node(state: PlanCraftState) -> PlanCraftState:
    """
    포맷팅 Agent 실행 노드

    LangSmith: run_name="📋 최종 포맷팅", tags=["agent", "output", "final"]

    Side-Effect: LLM 호출 (Azure OpenAI)

    처리 단계:
    1. Draft → Final Output 변환 (마크다운 조합)
    2. 웹 출처 링크 추가 (참고 자료 섹션)
    3. Formatter Agent 호출 (chat_summary 생성)
    4. refine_count 리셋 (사용자 수정 기회 3회 부여)

    재시도 안전: 포맷팅만 수행, 외부 상태 변경 없음
    """
    import time
    start_time = time.time()
    
    # =========================================================================
    # 1단계: Draft -> Final Output 변환
    # =========================================================================
    draft = state.get("draft")
    structure = state.get("structure")
    final_md = ""

    if draft:
        from graph.state import ensure_dict

        # Title 추출
        title = "기획서"
        if structure:
            structure_dict = ensure_dict(structure)
            title = structure_dict.get("title", "기획서")

        final_md = f"# {title}\n\n"

        # Sections 추출
        draft_dict = ensure_dict(draft)
        sections = draft_dict.get("sections", [])

        for sec in sections:
            sec_dict = ensure_dict(sec)
            name = sec_dict.get("name", "")
            content = sec_dict.get("content", "")
            final_md += f"## {name}\n\n{content}\n\n"

        # 웹 검색 출처 추가
        # [UPDATE] Writer가 생성한 참고 자료 섹션 제거 후 링크 포함된 섹션으로 교체
        web_sources = state.get("web_sources") or []
        web_urls = state.get("web_urls") or []
        web_context = state.get("web_context") or ""

        # Writer가 생성한 참고 자료 섹션 제거 (링크 없는 텍스트만 있는 경우)
        # 패턴: ## 참고 자료 또는 ## 참고자료 부터 다음 ## 또는 문서 끝까지
        reference_pattern = r'\n*#{1,2}\s*참고\s*자료.*?(?=\n#{1,2}\s|\Z)'
        final_md = re.sub(reference_pattern, '', final_md, flags=re.DOTALL)

        # 웹 소스가 있으면 링크 포함된 참고 자료 섹션 추가
        if web_sources:
            final_md += "---\n\n## 📚 참고 자료\n\n"
            final_md += "> 본 기획서 작성 시 다음 자료를 참고하였습니다.\n\n"
            for i, source in enumerate(web_sources, 1):
                title = source.get("title", "")
                url = source.get("url", "")
                # 제목이 비어있거나 URL과 동일한 경우 도메인명 추출
                if not title or title == url:
                    parsed = urlparse(url)
                    title = parsed.netloc.replace("www.", "") if parsed.netloc else "출처"
                final_md += f"{i}. [{title}]({url})\n"
            final_md += "\n"
        elif web_urls:
            # Fallback: URL만 있는 경우 도메인명 추출
            final_md += "---\n\n## 📚 참고 자료\n\n"
            final_md += "> 본 기획서 작성 시 다음 자료를 참고하였습니다.\n\n"
            for i, url in enumerate(web_urls, 1):
                parsed = urlparse(url)
                domain = parsed.netloc.replace("www.", "") if parsed.netloc else "출처"
                final_md += f"{i}. [{domain}]({url})\n"
            final_md += "\n"
        elif web_context and "웹 검색 결과" in web_context:
            final_md += "---\n\n## 📚 참고 자료\n\n"
            final_md += "> 본 기획서는 웹 검색을 통해 수집한 최신 정보를 반영하였습니다.\n\n"
        else:
            # [FIX] 웹 검색 결과가 없어도 RAG 기반 출처 표시
            rag_context = state.get("rag_context")
            if rag_context:
                final_md += "---\n\n## 📚 참고 자료\n\n"
                final_md += "> 본 기획서는 PlanCraft 내부 기획 가이드를 참고하여 작성되었습니다.\n\n"
                final_md += "- PlanCraft 기획서 작성 가이드\n"
                final_md += "- 사용자 여정 가이드\n"
                final_md += "- 서비스 기획 베스트 프랙티스\n\n"

    # =========================================================================
    # 2단계: Formatter Agent 호출 (chat_summary 생성 + refine_count=0 리셋)
    # =========================================================================
    state_with_output = update_state(state, final_output=final_md, current_step="format")
    new_state = formatter_run(state_with_output)

    return update_step_history(
        new_state, "format", "SUCCESS", summary="최종 포맷팅 및 교정 완료", start_time=start_time
    )
