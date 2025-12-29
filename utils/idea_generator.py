
import random
from utils.llm import get_llm
from utils.schemas import CreativeIdeaList
from utils.prompt_examples import WEB_APP_POOL, NON_IT_POOL

SYSTEM_PROMPT = """
당신은 실리콘밸리의 유니콘 스타트업 액셀러레이터입니다.
사람들이 "와우"할 만한 혁신적인 아이디어를 제안해야 합니다.

조건:
1. 흔한 아이디어(예: 단순 쇼핑몰, 투두리스트)는 절대 제외하세요.
2. AI, 블록체인, O2O, 핀테크 등 최신 기술을 접목한 IT 아이디어를 포함하세요.
3. ⚠️ **필수**: 최소 1개는 비IT 사업 아이디어를 포함하세요!
   - 비IT 예시: 카페 창업, 제조업, 프랜차이즈, 오프라인 서비스, 공방, 유통업 등
4. '제목'은 이모지를 포함해 직관적이고 매력적으로 지으세요.
5. '설명'은 이 에이전트에게 그대로 기획 요청을 보낼 수 있도록 구체적인 프롬프트 형태여야 합니다.
"""


def _has_non_it_idea(ideas: list) -> bool:
    """아이디어 목록에 비IT 아이디어가 있는지 확인"""
    non_it_keywords = ["창업", "제조", "프랜차이즈", "카페", "공방", "오프라인", "공장", 
                       "정육점", "베이커리", "미용실", "학원", "배달", "렌탈", "공간", 
                       "서점", "캠핑", "웨딩", "비누", "숙성", "농장", "도시락"]
    
    for _, desc in ideas:
        for keyword in non_it_keywords:
            if keyword in desc:
                return True
    return False


def generate_creative_ideas(count: int = 3) -> list:
    """
    LLM을 사용하여 창의적인 아이디어를 생성합니다.
    ⚠️ 최소 1개는 비IT 아이디어가 포함됩니다.
    
    Returns:
        List[Tuple[str, str]]: [(제목, 프롬프트), ...] 형식의 리스트
    """
    try:
        # LLM 호출
        llm = get_llm(temperature=0.9).with_structured_output(CreativeIdeaList)
        
        user_msg = f"""기발하고 혁신적인 스타트업 아이디어 {count}개를 제안해줘. 
⚠️ 중요: 최소 1개는 비IT 사업 아이디어(카페, 제조업, 프랜차이즈 등)를 포함해!
한국어로 작성해."""
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ]
        
        result = llm.invoke(messages)
        
        if not result or not result.ideas:
            raise ValueError("Empty result from LLM")
            
        ideas = [(idea.title, idea.description) for idea in result.ideas]
        
        # [NEW] 비IT 아이디어가 없으면 강제 추가
        if not _has_non_it_idea(ideas) and len(ideas) > 0:
            print("[INFO] 비IT 아이디어 누락 → 강제 추가")
            # 하나 제거하고 비IT 추가
            ideas.pop()
            ideas.append(random.choice(NON_IT_POOL))
        
        # 목록이 부족하면 Static에서 채움
        if len(ideas) < count:
            fallback = random.sample(WEB_APP_POOL + NON_IT_POOL, count - len(ideas))
            ideas.extend(fallback)
            
        return ideas[:count]

    except Exception as e:
        print(f"[WARN] 아이디어 생성 실패 (Fallback 작동): {e}")
        # Fallback: IT 2개 + 비IT 1개 보장
        it_ideas = random.sample(WEB_APP_POOL, min(count - 1, len(WEB_APP_POOL)))
        non_it_idea = random.choice(NON_IT_POOL)
        return it_ideas + [non_it_idea]

