"""
PlanCraft Reviewer Agent - 기획서 평가 및 심사
"""
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import JudgeResult
from graph.state import PlanCraftState, update_state
from prompts.reviewer_prompt import REVIEWER_SYSTEM_PROMPT

# LLM 초기화 (Structured Output)
reviewer_llm = get_llm(temperature=0.1).with_structured_output(JudgeResult)


def run(state: PlanCraftState) -> PlanCraftState:
    """
    기획서 검토 에이전트 실행
    
    작성된 초안(DraftResult)을 평가하고 개선점을 도출합니다.
    """
    
    # 1. 입력 데이터 준비
    draft = state.get("draft")
    if not draft:
        return update_state(state, error="검토할 초안이 없습니다.")
    
    # Draft 내용 추출
    if isinstance(draft, dict):
        sections = draft.get("sections", [])
    else:
        sections = getattr(draft, "sections", [])
        
    full_text = "\n\n".join([f"## {s.get('name', '')}\n{s.get('content', '')}" if isinstance(s, dict) else f"## {s.name}\n{s.content}" for s in sections])
    
    topic = "N/A"
    analysis = state.get("analysis")
    if analysis:
        topic = analysis.get("topic") if isinstance(analysis, dict) else getattr(analysis, "topic", "N/A")
    
    # 2. 프롬프트 구성
    messages = [
        SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
        HumanMessage(content=f"""
<topic>
{topic}
</topic>

<draft>
{full_text}
</draft>

위 기획서 초안을 평가하고 수정 보완할 점을 제안해주세요.
""")
    ]
    
    # 3. LLM 호출
    try:
        review_result = reviewer_llm.invoke(messages)
        
        # 4. 상태 업데이트
        if hasattr(review_result, "model_dump"):
            review_dict = review_result.model_dump()
        else:
            review_dict = review_result
            
        return update_state(
            state,
            review=review_dict,
            current_step="review"
        )
        
    except Exception as e:
        print(f"[ERROR] Reviewer Failed: {e}")
        return update_state(state, error=str(e))
