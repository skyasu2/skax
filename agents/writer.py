"""
PlanCraft Agent - Writer Agent

설계된 구조에 따라 기획서 내용을 작성하는 Agent입니다.
각 섹션별로 구체적이고 전문적인 내용을 생성합니다.

주요 기능:
    - 섹션별 내용 작성
    - 마크다운 형식 출력
    - 개조식/넘버링 활용
    - 구체적 수치 제시

입력:
    - user_input: 원본 사용자 입력
    - structure: 기획서 구조
    - rag_context: RAG 검색 결과 (선택)

출력:
    - draft: 초안 딕셔너리

Best Practice 적용:
    - with_structured_output(): LangChain 표준 Structured Output 패턴
    - PlanCraftState 타입 어노테이션: 명시적 입출력 타입
"""

import json
from utils.llm import get_llm
from utils.schemas import DraftResult
from graph.state import PlanCraftState
from prompts.writer_prompt import WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT


class WriterAgent:
    """
    기획서 내용을 작성하는 Agent

    LangChain의 with_structured_output()을 사용하여
    Pydantic 스키마 기반의 구조화된 출력을 생성합니다.

    Attributes:
        llm: AzureChatOpenAI 인스턴스 (Structured Output 적용)
    """

    def __init__(self, model_type: str = "gpt-4o"):
        """
        Writer Agent를 초기화합니다.

        Args:
            model_type: 사용할 LLM 모델
        """
        # 작성은 창의성이 필요하므로 높은 temperature 사용
        base_llm = get_llm(model_type=model_type, temperature=0.7)

        # with_structured_output: LangChain Best Practice
        self.llm = base_llm.with_structured_output(DraftResult)

    def run(self, state: PlanCraftState) -> PlanCraftState:
        """
        기획서 내용을 작성합니다.

        Args:
            state: 현재 워크플로우 상태 (PlanCraftState)
                - user_input: 원본 입력
                - structure: 기획서 구조 (필수)
                - rag_context: RAG 컨텍스트 (선택)

        Returns:
            PlanCraftState: 업데이트된 상태
                - draft: 작성된 초안
                - current_step: "write"
        """
        # =====================================================================
        # 1. 입력 데이터 추출
        # =====================================================================
        user_input = state.user_input
        # structure는 Pydantic 객체임
        structure = state.structure
        structure_dict = structure.model_dump() if structure else {}
        context = state.rag_context

        # =====================================================================
        # 2. Structured Output으로 LLM 호출
        # =====================================================================
        messages = [
            {"role": "system", "content": WRITER_SYSTEM_PROMPT},
            {"role": "user", "content": WRITER_USER_PROMPT.format(
                user_input=user_input,
                structure=json.dumps(structure_dict, ensure_ascii=False, indent=2),
                context=context if context else "없음"
            )}
        ]

        try:
            # Pydantic 객체 그대로 사용
            draft: DraftResult = self.llm.invoke(messages)
            
        except Exception as e:
            # 실패 시 기본 초안 객체 생성
            from utils.schemas import SectionContent
            
            draft = DraftResult(
                sections=[
                    SectionContent(id=1, name="초안 작성 오류", content=f"작성 중 오류가 발생했습니다: {str(e)}")
                ]
            )
            state.error = f"초안 작성 오류: {str(e)}"

        # =====================================================================
        # 3. [개선] 웹/참고 자료 출처 섹션 자동 추가
        # =====================================================================
        web_context = state.web_context
        web_urls = getattr(state, "web_urls", [])

        if (web_context or web_urls) and draft and draft.sections:
            unique_refs = set()
            references = []
            
            # 1. 명시적인 URL 목록 (web_urls) 우선 활용
            if web_urls:
                for url in web_urls:
                    if url and isinstance(url, str) and url not in unique_refs:
                        references.append(f"- [웹 검색 결과]({url})")
                        unique_refs.add(url)

            # 2. web_context에서 링크 추출 (보완)
            if web_context:
                import re
                
                # 마크다운 링크 패턴: [Title](URL)
                md_links = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', web_context)
                for title, url in md_links:
                    if url not in unique_refs:
                        clean_title = title.strip()[:60] + "..." if len(title) > 60 else title
                        references.append(f"- [{clean_title}]({url})")
                        unique_refs.add(url)
                
                # 일반 URL 패턴 (마크다운 링크를 제외한)
                raw_urls = re.findall(r'(https?://[a-zA-Z0-9\.\/\-\?=&%_]+)', web_context)
                for url in raw_urls:
                    # 괄호나 문장 부호로 끝나는 경우 정리
                    url = url.rstrip(').,;]\'"')
                    if url and url not in unique_refs:
                        references.append(f"- [추가 자료]({url})")
                        unique_refs.add(url)

            if references:
                from utils.schemas import SectionContent
                ref_content = "\n".join(references)
                
                ref_section = SectionContent(
                    id=len(draft.sections) + 1,
                    name="📚 참고 자료",
                    content=f"본 기획서는 다음의 웹 검색 결과 및 참고 자료를 바탕으로 작성되었습니다.\n\n{ref_content}"
                )
                draft.sections.append(ref_section)

        # =====================================================================
        # 4. 상태 업데이트
        # =====================================================================
        new_state = state.model_copy(update={
            "draft": draft,
            "current_step": "write"
        })

        return new_state

    def format_as_markdown(self, draft: DraftResult) -> str:
        """
        draft 객체를 마크다운 형식으로 변환합니다.

        Args:
            draft: 초안 객체 (DraftResult)

        Returns:
            str: 마크다운 형식 문자열
        """
        md_content = []
        
        # draft가 Pydantic 객체이므로 sections 리스트에 접근
        sections = draft.sections if draft else []

        for section in sections:
            md_content.append(f"## {section.name}")
            md_content.append("")
            md_content.append(section.content)
            md_content.append("")

        return "\n".join(md_content)


def run(state: PlanCraftState) -> PlanCraftState:
    """LangGraph 노드용 함수"""
    agent = WriterAgent()
    return agent.run(state)
