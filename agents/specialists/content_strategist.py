"""
PlanCraft Agent - Content Strategist Specialist
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import AgentResponse
import json

CONTENT_SYSTEM_PROMPT = """당신은 **Content & Brand Strategist (CMO급)**입니다.

## 역할
서비스의 성공을 위한 **브랜딩, 콘텐츠 전략, 사용자 유입(AARRR) 전략**을 수립합니다.
기술적 기능보다는 '사용자가 왜 이 서비스를 써야 하는가(Why)'에 집중합니다.

## 분석 포인트
1. **Brand Concept**: 서비스의 페르소나, 톤앤매너, 슬로건
2. **Core Message**: 타겟 사용자에게 전달할 단 하나의 핵심 메시지
3. **Content Strategy**: 블로그, SNS, 커뮤니티 등 채널별 콘텐츠 운영 방안
4. **User Acquisition**: 초기 사용자 1,000명 확보를 위한 게릴라 마케팅 전략

## 출력 형식 (JSON)
{
    "brand_concept": {
        "persona": "...",
        "slogan": "...",
        "tone_and_manner": "..."
    },
    "core_message": "...",
    "content_channels": ["...", "..."],
    "acquisition_strategy": "..."
}
"""

def run_content_strategist(context: dict) -> dict:
    """Content Strategist 에이전트 실행"""
    llm = get_llm(temperature=0.7)  # 마케팅은 창의적이어야 함
    
    user_input = context.get("service_overview", "")
    target_users = context.get("target_users", "")
    market_data = context.get("market_analysis", {})
    
    prompt = f"""
## 서비스 개요
{user_input}

## 타겟 사용자
{target_users}

## 시장 배경
{json.dumps(market_data, ensure_ascii=False)[:500]}...

위 내용을 바탕으로 매력적인 콘텐츠 및 브랜딩 전략을 수립해주세요.
반드시 JSON 형식으로 출력하세요.
"""
    
    try:
        response = llm.invoke([
            SystemMessage(content=CONTENT_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ])
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "")
        
        return json.loads(content)
        
    except Exception as e:
        print(f"[ContentStrategist] Error: {e}")
        return {"error": str(e)}
