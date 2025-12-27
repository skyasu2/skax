# PlanCraft Agent - API 명세서

## 1. 핵심 함수

### 1.1 워크플로우 실행

```python
from graph.workflow import run_plancraft

result = run_plancraft(
    user_input: str,           # 필수: 사용자 입력
    file_content: str = None   # 선택: 참고 파일 내용
) -> dict
```

#### 반환값

```python
{
    "final_output": str,       # 생성된 기획서 (마크다운)
    "analysis": dict,          # 분석 결과
    "structure": dict,         # 구조 설계
    "review": dict,            # 검토 결과
    "need_more_info": bool,    # 추가 정보 필요 여부
    "questions": list,         # 추가 질문 (need_more_info=True 시)
    "web_context": str,        # 웹 검색 결과 (있을 경우)
}
```

---

## 2. Agent API

### 2.1 Analyzer Agent

```python
from agents.analyzer import run

state = run(state: PlanCraftState) -> PlanCraftState
```

#### 입력 State 필드
- `user_input`: 사용자 입력
- `file_content`: 참고 파일 (선택)
- `rag_context`: RAG 검색 결과
- `web_context`: 웹 검색 결과

#### 출력 State 필드
- `analysis`: 분석 결과 딕셔너리
- `need_more_info`: 추가 정보 필요 여부
- `questions`: 추가 질문 목록

---

### 2.2 Structurer Agent

```python
from agents.structurer import run

state = run(state: PlanCraftState) -> PlanCraftState
```

#### 출력 State 필드
- `structure`: 구조 설계 결과
  ```python
  {
      "title": "기획서 제목",
      "sections": [
          {"id": 1, "name": "개요", "description": "...", "key_points": [...]},
          ...
      ]
  }
  ```

---

### 2.3 Writer Agent

```python
from agents.writer import run

state = run(state: PlanCraftState) -> PlanCraftState
```

#### 출력 State 필드
- `draft`: 작성된 초안
  ```python
  {
      "sections": [
          {"id": 1, "name": "개요", "content": "마크다운 내용..."},
          ...
      ]
  }
  ```

---

### 2.4 Reviewer Agent

```python
from agents.reviewer import run

state = run(state: PlanCraftState) -> PlanCraftState
```

#### 출력 State 필드
- `review`: 검토 결과
  ```python
  {
      "overall_score": 8,
      "strengths": ["강점1", "강점2"],
      "improvements": ["개선점1", "개선점2"],
      "suggestions": ["제안1", "제안2"],
      "is_ready": True
  }
  ```
- `final_output`: 최종 기획서 (마크다운)

---

## 3. 웹 검색 API

### 3.1 조건부 검색

```python
from mcp.web_search import conditional_web_search

result = conditional_web_search(
    user_input: str,
    rag_context: str = ""
) -> dict
```

#### 반환값

```python
{
    "searched": bool,      # 검색 수행 여부
    "reason": str,         # 판단 이유
    "context": str         # 검색 결과 (searched=True 시)
}
```

### 3.2 검색 필요 여부 판단

```python
from mcp.web_search import should_search_web

result = should_search_web(
    user_input: str,
    rag_context: str = ""
) -> dict
```

#### 반환값

```python
{
    "should_search": bool,  # 검색 필요 여부
    "reason": str,          # 판단 이유
    "search_query": str     # 검색 쿼리 (should_search=True 시)
}
```

### 3.3 직접 웹 검색

```python
from mcp.web_search import search_web

result = search_web(
    query: str,
    max_results: int = 5
) -> dict
```

#### 반환값

```python
{
    "success": bool,
    "query": str,
    "results": [
        {"title": "...", "url": "...", "snippet": "..."},
        ...
    ],
    "formatted": str,      # 포맷팅된 텍스트
    "source": "duckduckgo"
}
```

---

## 4. URL Fetch API

```python
from mcp.web_client import fetch_url_sync

content = fetch_url_sync(
    url: str,
    max_length: int = 5000
) -> str
```

---

## 5. 파일 유틸리티

### 5.1 기획서 저장

```python
from mcp.file_utils import save_plan

path = save_plan(
    content: str,
    filename: str = None  # None이면 타임스탬프 자동 생성
) -> str  # 저장된 파일 경로
```

### 5.2 저장된 기획서 목록

```python
from mcp.file_utils import list_saved_plans

files = list_saved_plans(
    limit: int = 10
) -> List[str]  # 파일 경로 목록 (최신순)
```

---

## 6. RAG API

### 6.1 벡터스토어 초기화

```python
from rag.vectorstore import init_vectorstore

vectorstore = init_vectorstore() -> FAISS
```

### 6.2 문서 검색

```python
from rag.retriever import Retriever

retriever = Retriever(k=3)
context = retriever.get_formatted_context(query: str) -> str
```

---

## 7. 설정 API

```python
from utils.config import Config

# 환경변수 검증
Config.validate()  # 실패 시 EnvironmentError

# 설정값 접근
endpoint = Config.AOAI_ENDPOINT
api_key = Config.AOAI_API_KEY
```

---

## 8. LLM 클라이언트

```python
from utils.llm import get_llm, get_embeddings

# Chat 모델
llm = get_llm(
    model_type: str = "gpt-4o",  # "gpt-4o" 또는 "gpt-4o-mini"
    temperature: float = 0.7
) -> AzureChatOpenAI

# Embedding 모델
embeddings = get_embeddings() -> AzureOpenAIEmbeddings
```
