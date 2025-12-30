# Agent 입출력 JSON 예시

> 각 에이전트의 실제 입출력 데이터 예시입니다. 온보딩, 테스트, 디버깅에 활용하세요.

## 목차

1. [Analyzer Agent](#1-analyzer-agent)
2. [Structurer Agent](#2-structurer-agent)
3. [Writer Agent](#3-writer-agent)
4. [Reviewer Agent](#4-reviewer-agent)
5. [Refiner Agent](#5-refiner-agent)
6. [Formatter Agent](#6-formatter-agent)
7. [HITL Interrupt Payload](#7-hitl-interrupt-payload)

---

## 1. Analyzer Agent

### 입력 (State에서 추출)

```json
{
  "user_input": "직장인을 위한 점심 메뉴 추천 앱을 만들고 싶어요",
  "file_content": null,
  "rag_context": "기획서 작성 가이드: 1. 문제 정의...",
  "web_context": "2024년 직장인 점심 시장 규모 약 15조원..."
}
```

### 출력 (AnalysisResult)

```json
{
  "topic": "직장인 점심 메뉴 추천 서비스",
  "purpose": "매일 반복되는 메뉴 선택 고민을 AI로 해결",
  "target_users": "20-40대 직장인, 사무실 근무자",
  "key_features": [
    "위치 기반 맛집 추천",
    "개인 취향 학습",
    "그룹 투표 기능",
    "예산별 필터링"
  ],
  "assumptions": [
    "모바일 앱으로 개발 (iOS/Android)",
    "MVP는 서울 지역부터 시작",
    "수익 모델은 광고 + 프리미엄 구독"
  ],
  "missing_info": [],
  "options": [],
  "option_question": "",
  "is_general_query": false,
  "general_answer": null,
  "doc_type": "web_app_plan",
  "need_more_info": false
}
```

### 짧은 입력 시 (HITL 트리거)

```json
{
  "topic": "점심 앱",
  "purpose": "",
  "target_users": "",
  "key_features": [],
  "assumptions": [],
  "missing_info": ["구체적인 서비스 방향"],
  "options": [
    {
      "title": "AI 맛집 추천",
      "description": "사용자 취향을 학습하여 개인화된 맛집을 추천하는 서비스"
    },
    {
      "title": "그룹 점심 투표",
      "description": "팀원들이 함께 메뉴를 투표로 결정하는 협업 도구"
    },
    {
      "title": "점심 배달 중개",
      "description": "사무실 단체 배달을 쉽게 주문할 수 있는 플랫폼"
    }
  ],
  "option_question": "어떤 방향의 서비스를 원하시나요?",
  "is_general_query": false,
  "general_answer": null,
  "doc_type": "web_app_plan",
  "need_more_info": true
}
```

---

## 2. Structurer Agent

### 입력 (State에서 추출)

```json
{
  "analysis": {
    "topic": "직장인 점심 메뉴 추천 서비스",
    "purpose": "메뉴 선택 고민 해결",
    "target_users": "20-40대 직장인",
    "key_features": ["위치 기반 추천", "개인화", "그룹 투표"]
  },
  "rag_context": "기획서 필수 섹션: 개요, 시장분석, 기술스택..."
}
```

### 출력 (StructureResult)

```json
{
  "title": "LunchMate - 직장인 점심 메뉴 추천 서비스 기획서",
  "sections": [
    {
      "id": 1,
      "name": "프로젝트 개요",
      "description": "서비스 소개, 목표, 예상 기간",
      "key_points": ["한줄 요약", "프로젝트 유형", "목표 시점"]
    },
    {
      "id": 2,
      "name": "문제 정의 및 해결책",
      "description": "현황 분석, Pain Point, Solution",
      "key_points": ["타겟 고객의 불편함", "Why Now", "차별화 포인트"]
    },
    {
      "id": 3,
      "name": "시장 분석",
      "description": "TAM/SAM/SOM, 경쟁사 분석",
      "key_points": ["시장 규모", "경쟁사 3개 이상", "포지셔닝"]
    },
    {
      "id": 4,
      "name": "타겟 사용자",
      "description": "페르소나, 사용자 여정",
      "key_points": ["Primary/Secondary 타겟", "User Journey"]
    },
    {
      "id": 5,
      "name": "핵심 기능",
      "description": "MVP 기능 목록",
      "key_points": ["기능 우선순위", "차별화 기능"]
    },
    {
      "id": 6,
      "name": "비즈니스 모델",
      "description": "수익 구조, 가격 정책",
      "key_points": ["수익원", "예상 매출"]
    },
    {
      "id": 7,
      "name": "기술 스택",
      "description": "아키텍처, 사용 기술",
      "key_points": ["Frontend/Backend/DB/Infra"]
    },
    {
      "id": 8,
      "name": "일정 및 마일스톤",
      "description": "개발 로드맵",
      "key_points": ["주차별 목표", "담당자"]
    },
    {
      "id": 9,
      "name": "리스크 및 대응",
      "description": "예상 리스크와 완화 방안",
      "key_points": ["기술/운영/재무 리스크"]
    },
    {
      "id": 10,
      "name": "기대 효과 및 KPI",
      "description": "성과 지표",
      "key_points": ["MAU/DAU", "전환율", "NPS"]
    }
  ]
}
```

---

## 3. Writer Agent

### 입력 (State에서 추출)

```json
{
  "structure": {
    "title": "LunchMate 기획서",
    "sections": [
      {"id": 1, "name": "프로젝트 개요", "key_points": ["한줄 요약"]}
    ]
  },
  "analysis": {
    "topic": "직장인 점심 메뉴 추천",
    "purpose": "메뉴 고민 해결"
  },
  "rag_context": "...",
  "web_context": "시장 규모 15조원..."
}
```

### 출력 (DraftResult)

```json
{
  "sections": [
    {
      "id": 1,
      "name": "프로젝트 개요",
      "content": "**프로젝트명**: LunchMate\n**한줄 요약**: AI 기반 직장인 점심 메뉴 추천 서비스\n**유형**: 신규 개발\n**예상 기간**: 3개월 (2025.01 ~ 2025.03)"
    },
    {
      "id": 2,
      "name": "문제 정의 및 해결책",
      "content": "### 현황 분석\n직장인의 78%가 매일 점심 메뉴 선택에 평균 15분을 소비합니다.\n\n### Pain Point\n- 매일 반복되는 메뉴 고민\n- 팀원 간 의견 조율 어려움\n\n### Solution\n- AI가 취향을 학습하여 개인화 추천\n- 그룹 투표로 빠른 의사결정"
    },
    {
      "id": 3,
      "name": "시장 분석",
      "content": "### 시장 규모\n| 구분 | 규모 |\n|------|------|\n| TAM | 15조원 |\n| SAM | 3조원 |\n| SOM | 300억원 |\n\n### 경쟁사 분석\n| 경쟁사 | 특징 | 한계 |\n|--------|------|------|\n| 배달의민족 | 배달 중심 | 외식 추천 부족 |\n| 망고플레이트 | 리뷰 중심 | 개인화 부족 |"
    }
  ]
}
```

---

## 4. Reviewer Agent

### 입력 (State에서 추출)

```json
{
  "draft": {
    "sections": [
      {"id": 1, "name": "프로젝트 개요", "content": "..."},
      {"id": 2, "name": "문제 정의", "content": "..."}
    ]
  },
  "rag_context": "품질 체크리스트: 1. 논리적 흐름..."
}
```

### 출력 (JudgeResult) - PASS 예시

```json
{
  "overall_score": 9,
  "verdict": "PASS",
  "critical_issues": [],
  "strengths": [
    "시장 분석이 구체적인 수치와 함께 제시됨",
    "경쟁사 분석이 표로 명확하게 정리됨",
    "기술 스택이 현실적이고 구현 가능함"
  ],
  "weaknesses": [
    "리스크 대응 방안이 다소 일반적임"
  ],
  "action_items": [],
  "reasoning": "전반적으로 완성도가 높은 기획서입니다. 시장 분석과 비즈니스 모델이 논리적으로 연결되어 있습니다."
}
```

### 출력 (JudgeResult) - REVISE 예시

```json
{
  "overall_score": 6,
  "verdict": "REVISE",
  "critical_issues": [
    "시장 규모 근거 데이터 출처가 없음"
  ],
  "strengths": [
    "핵심 기능이 명확하게 정의됨"
  ],
  "weaknesses": [
    "경쟁사 분석이 2개사로 부족함",
    "수익 모델의 구체적인 수치가 없음",
    "일정이 비현실적으로 촉박함"
  ],
  "action_items": [
    "경쟁사를 최소 3개 이상으로 확대",
    "시장 규모에 출처 명시",
    "예상 매출 산정 근거 추가"
  ],
  "reasoning": "기본 구조는 갖추었으나 시장 분석과 재무 계획의 구체성이 부족합니다."
}
```

### 출력 (JudgeResult) - FAIL 예시

```json
{
  "overall_score": 3,
  "verdict": "FAIL",
  "critical_issues": [
    "핵심 기능이 정의되지 않음",
    "타겟 사용자가 불명확함",
    "비즈니스 모델이 없음"
  ],
  "strengths": [],
  "weaknesses": [
    "전반적인 내용이 피상적임",
    "기획서라기보다 아이디어 메모 수준"
  ],
  "action_items": [
    "처음부터 재분석 필요",
    "사용자 정의부터 다시 시작"
  ],
  "reasoning": "기획서의 기본 요건을 충족하지 못합니다. 재분석이 필요합니다."
}
```

---

## 5. Refiner Agent

### 입력 (State에서 추출)

```json
{
  "review": {
    "overall_score": 6,
    "verdict": "REVISE",
    "feedback_summary": "시장 분석 보강 필요",
    "critical_issues": ["경쟁사 분석 부족"],
    "action_items": ["경쟁사 3개 이상 추가"]
  },
  "draft": {
    "sections": [...]
  },
  "refine_count": 0
}
```

### 출력 (RefinementStrategy)

```json
{
  "overall_direction": "시장 분석 섹션을 중심으로 데이터 기반 보강",
  "key_focus_areas": [
    "경쟁사 분석 확대 (3개 → 5개)",
    "시장 규모 출처 명시",
    "수익 모델 수치화"
  ],
  "specific_guidelines": [
    "경쟁사 분석에 카카오맵, 네이버지도, 식신 추가",
    "시장 규모에 통계청 또는 업계 리포트 출처 명시",
    "예상 매출을 MAU 기반으로 산정하여 제시"
  ],
  "additional_search_keywords": [
    "2024 외식 시장 규모",
    "점심 배달 시장 성장률"
  ]
}
```

---

## 6. Formatter Agent

### 입력 (State에서 추출)

```json
{
  "draft": {
    "sections": [...]
  },
  "structure": {
    "title": "LunchMate 기획서"
  },
  "web_sources": [
    {"title": "통계청 외식산업 동향", "url": "https://kostat.go.kr/..."},
    {"title": "배달앱 시장 분석 - 한국경제", "url": "https://hankyung.com/..."}
  ]
}
```

### 출력 (State 업데이트)

```json
{
  "final_output": "# LunchMate 기획서\n\n## 프로젝트 개요\n...\n\n---\n\n## 📚 참고 자료\n\n1. [통계청 외식산업 동향](https://kostat.go.kr/...)\n2. [배달앱 시장 분석 - 한국경제](https://hankyung.com/...)",
  "chat_summary": "직장인 점심 추천 앱 'LunchMate' 기획서를 완성했습니다. 10개 섹션으로 구성되었으며, 시장 분석과 비즈니스 모델이 포함되어 있습니다.",
  "refine_count": 0
}
```

---

## 7. HITL Interrupt Payload

### Option 타입 (선택지 제시)

```json
{
  "type": "option",
  "question": "어떤 방향의 서비스를 원하시나요?",
  "options": [
    {
      "title": "AI 맛집 추천",
      "description": "사용자 취향을 학습하여 개인화된 맛집을 추천"
    },
    {
      "title": "그룹 점심 투표",
      "description": "팀원들이 함께 메뉴를 투표로 결정"
    },
    {
      "title": "점심 배달 중개",
      "description": "사무실 단체 배달 주문 플랫폼"
    }
  ],
  "input_schema_name": null,
  "data": {
    "retry_count": 0
  }
}
```

### Resume 입력 (사용자 응답)

```json
{
  "selected_option": {
    "id": "1",
    "title": "AI 맛집 추천",
    "description": "사용자 취향을 학습하여 개인화된 맛집을 추천"
  },
  "text_input": null
}
```

### 직접 입력 Resume

```json
{
  "selected_option": null,
  "text_input": "AI 맛집 추천 + 그룹 투표 기능을 함께 넣어주세요"
}
```

---

## 테스트 활용 예시

```python
import pytest
from utils.schemas import AnalysisResult, StructureResult, DraftResult, JudgeResult

def test_analysis_result_parsing():
    """Analyzer 출력 파싱 테스트"""
    data = {
        "topic": "점심 추천 앱",
        "purpose": "메뉴 고민 해결",
        "target_users": "직장인",
        "key_features": ["위치 기반 추천"],
        "need_more_info": False
    }
    result = AnalysisResult(**data)
    assert result.topic == "점심 추천 앱"
    assert result.need_more_info == False

def test_judge_result_verdict_validation():
    """Reviewer verdict 자동 보정 테스트"""
    data = {
        "overall_score": 7,
        "verdict": "revise",  # 소문자 입력
        "critical_issues": [],
        "strengths": ["좋음"],
        "weaknesses": ["보완 필요"],
        "action_items": []
    }
    result = JudgeResult(**data)
    assert result.verdict == "REVISE"  # 자동 대문자 변환
```

---

## 관련 파일

| 파일 | 설명 |
|------|------|
| `utils/schemas.py` | Pydantic 스키마 정의 |
| `agents/*.py` | 각 에이전트 구현 |
| `graph/state.py` | PlanCraftState TypedDict |
| `tests/test_scenarios.py` | 통합 테스트 |
