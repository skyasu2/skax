# PlanCraft Agent - 웹 검색 설계 문서

## 1. 설계 목표

### 1.1 핵심 원칙

> **"자동 = 무조건" ❌**
> **"자동 = 조건부 판단" ✅**

본 시스템은 최신성이 요구되는 질의에 한해 MCP 기반 웹검색을 **선택적으로** 수행합니다.

### 1.2 설계 의도

| 목표 | 구현 방법 |
|------|-----------|
| 불필요한 외부 호출 방지 | 조건부 판단 로직 |
| 비용 절감 | 필요한 경우에만 검색 |
| 응답 속도 향상 | RAG 우선 활용 |
| Agent 판단 능력 시연 | Supervisor 패턴 |

---

## 2. 조건부 검색 로직

### 2.1 판단 플로우차트

```
                    ┌─────────────┐
                    │ 사용자 입력  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ URL 포함?   │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
        ┌───────────┐            ┌───────────┐
        │ URL Fetch │            │ 키워드    │
        │  (직접)   │            │  분석     │
        └───────────┘            └─────┬─────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
              ┌───────────┐     ┌───────────┐     ┌───────────┐
              │ 최신성    │     │ 외부정보  │     │ 내부문서  │
              │ 키워드?   │     │ 키워드?   │     │ 키워드?   │
              └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
                    │                 │                 │
                    ▼                 ▼                 ▼
              ┌───────────┐     ┌───────────┐     ┌───────────┐
              │ 웹 검색   │     │ 웹 검색   │     │ 검색 스킵 │
              │ 수행 ✅   │     │ 수행 ✅   │     │      ❌   │
              └───────────┘     └───────────┘     └───────────┘
```

### 2.2 키워드 분류

#### 최신성 키워드 (웹 검색 수행)

```python
RECENCY_KEYWORDS = [
    # 시간 관련
    "최근", "최신", "요즘", "현재", "지금", "올해", "이번",
    "2024", "2025", "2026",
    "트렌드", "동향", "현황", "전망",
    # 영어
    "recent", "latest", "current", "trend", "now",
]
```

#### 외부 정보 키워드 (웹 검색 수행)

```python
EXTERNAL_KEYWORDS = [
    # 시장/경쟁
    "시장", "경쟁사", "경쟁", "업계", "산업",
    "사례", "벤치마크", "레퍼런스",
    # 기술
    "기술", "신기술", "혁신", "AI", "인공지능",
    # 통계
    "통계", "데이터", "수치", "규모",
    # 영어
    "market", "competitor", "industry", "case study",
]
```

#### 내부 문서 키워드 (웹 검색 스킵)

```python
INTERNAL_KEYWORDS = [
    "규정", "매뉴얼", "절차", "프로세스", "내부",
    "사내", "우리", "당사", "회사",
]
```

---

## 3. 검색 수행 예시

### 3.1 웹 검색이 수행되는 경우 ✅

| 입력 예시 | 감지 키워드 | 검색 쿼리 |
|-----------|-------------|-----------|
| "AI 헬스케어 최신 트렌드" | "최신", "AI" | "AI 헬스케어 트렌드 2025" |
| "2025년 SaaS 시장 규모" | "2025", "시장", "규모" | "2025 SaaS 시장 규모" |
| "경쟁사 벤치마크 분석" | "경쟁사", "벤치마크" | "경쟁사 벤치마크 2025" |
| "요즘 핫한 배달앱 기능" | "요즘", "핫한" | "배달앱 기능 트렌드 2025" |

### 3.2 웹 검색이 스킵되는 경우 ❌

| 입력 예시 | 스킵 이유 |
|-----------|-----------|
| "점심 메뉴 추천 앱" | 일반 기획 요청 |
| "사내 규정 기반 시스템" | 내부 문서 키워드 |
| "우리 회사 프로세스 개선" | 내부 문서 키워드 |
| "https://example.com 참고" | URL 직접 제공 (fetch로 대체) |

---

## 4. 기술 구현

### 4.1 파일 구조

```
mcp/
├── web_search.py      # 조건부 웹 검색
│   ├── should_search_web()      # 판단 함수
│   ├── search_web()             # DuckDuckGo 검색
│   └── conditional_web_search() # 통합 함수
│
└── web_client.py      # URL Fetch
    ├── fetch_url_sync()         # 동기 URL fetch
    └── WebClient                # 비동기 클라이언트
```

### 4.2 핵심 함수

```python
def conditional_web_search(user_input: str, rag_context: str) -> dict:
    """
    조건부 웹 검색 통합 함수

    1. should_search_web()로 검색 필요 여부 판단
    2. 필요시 search_web()으로 검색 수행
    3. 결과 반환

    Returns:
        {
            "searched": bool,
            "reason": str,
            "context": str
        }
    """
```

### 4.3 워크플로우 통합

```python
# graph/workflow.py

def fetch_web_context(state: PlanCraftState) -> PlanCraftState:
    """
    조건부 웹 정보 수집 노드 (Supervisor 역할)

    1. URL 직접 제공 → URL Fetch
    2. URL 없음 → conditional_web_search() 호출
    3. 검색 결과를 state["web_context"]에 저장
    """
```

---

## 5. Fallback 전략

### 5.1 DuckDuckGo 검색 실패 시

```python
def search_web(query: str) -> dict:
    try:
        from duckduckgo_search import DDGS
        # 정식 라이브러리 사용
    except ImportError:
        # Fallback: DuckDuckGo Instant Answer API
        return _fallback_search(query)
```

### 5.2 URL Fetch 실패 시

```python
def fetch_url_sync(url: str) -> str:
    try:
        # requests + BeautifulSoup
    except Exception:
        return "[웹 조회 실패]"
```

### 5.3 전체 웹 조회 실패 시

```python
# Graceful Degradation
state["web_context"] = None
state["web_urls"] = []
# 워크플로우 계속 진행 (RAG만으로 기획서 생성)
```

---

## 6. 로깅 및 모니터링

### 6.1 콘솔 출력

```
🔍 웹 검색 수행: 최신 정보 필요
📚 웹 검색 스킵: 내부 문서 질의
🔗 URL 직접 참조: 2개
⚠️ URL 조회 실패 (https://...): timeout
```

### 6.2 상태 추적

```python
state["web_context"]  # 검색 결과 (있을 경우)
state["web_urls"]     # 조회한 URL 목록
```

---

## 7. 심사 가점 요소

### 7.1 Agent 판단 능력 시연

- 무조건 검색 ❌
- 조건부 판단 후 검색 ✅

### 7.2 RAG와 역할 분리

- RAG = 내부/정적 지식
- Web Search = 외부/최신 정보

### 7.3 설계 의도 문서화

README에 명시:
> "본 시스템은 최신성이 요구되는 질의에 한해 MCP 기반 웹검색을 선택적으로 수행한다."

### 7.4 Graceful Degradation

- 검색 실패해도 기획서 생성 가능
- 사용자 경험 저하 없음

---

## 8. 확장 가이드

### 8.1 키워드 추가

```python
# mcp/web_search.py

RECENCY_KEYWORDS.append("새로운")
EXTERNAL_KEYWORDS.append("글로벌")
```

### 8.2 검색 엔진 변경

```python
# Tavily 사용 예시 (API 키 필요)
def search_web_tavily(query: str) -> dict:
    from tavily import TavilyClient
    client = TavilyClient(api_key="...")
    return client.search(query)
```

### 8.3 검색 결과 후처리

```python
def postprocess_search_results(results: list) -> str:
    # 중복 제거, 요약, 필터링 등
    pass
```
