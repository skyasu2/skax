"""
PlanCraft Agent - Tech Architect Specialist
"""
from langchain_core.messages import SystemMessage, HumanMessage
from utils.llm import get_llm
from utils.schemas import AgentResponse
from graph.state import PlanCraftState, update_state
import json

TECH_SYSTEM_PROMPT = """당신은 15년 경력의 **Technical Architect (CTO급)**입니다.

## 역할
제시된 서비스 기획안을 바탕으로 최적의 **기술 아키텍처와 개발 로드맵**을 설계합니다.
비즈니스 요구사항을 실현 가능한 기술 스택으로 변환하는 것이 목표입니다.

## 분석 포인트
1. **Tech Stack Recommendation**: 프론트엔드, 백엔드, DB, 인프라 등 (이유 포함)
2. **System Architecture**: 클라우드 구조, MSA vs Monolith 등
3. **Key Technical Challenges**: 예상되는 기술적 난관 및 해결 방안 (예: 실시간성, 대용량 처리)
4. **Development Roadmap**: MVP 단계별 개발 범위 및 추정 기간

## 출력 형식 (JSON)
{
    "recommended_stack": {
        "frontend": "...",
        "backend": "...",
        "database": "...",
        "infrastructure": "..."
    },
    "architecture_desc": "...",
    "technical_challenges": ["...", "..."],
    "roadmap": {
        "phase1_mvp": "...",
        "phase2_scale": "..."
    }
}
"""

def run_tech_architect(context: dict) -> dict:
    """Tech Architect 에이전트 실행"""
    llm = get_llm(temperature=0.3)  # 기술 설계는 명확해야 함
    
    user_input = context.get("service_overview", "")
    target_users = context.get("target_users", "")
    constraints = context.get("user_constraints", [])
    
    prompt = f"""
## 서비스 개요
{user_input}

## 타겟 사용자
{target_users}

## 제약 사항
{json.dumps(constraints, ensure_ascii=False)}

위 내용을 바탕으로 기술 아키텍처를 설계해주세요.
반드시 JSON 형식으로 출력하세요.
"""
    
    try:
        response = llm.invoke([
            SystemMessage(content=TECH_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ])
        
        # JSON 파싱 시도
        content = response.content.strip()
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "")
        
        return json.loads(content)
        
    except Exception as e:
        print(f"[TechArchitect] Error: {e}")
        return {
            "error": str(e),
            "recommended_stack": {"desc": "분석 실패 (기본 스택 권장)"}
        }
