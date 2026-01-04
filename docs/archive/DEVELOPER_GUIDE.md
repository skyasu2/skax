# PlanCraft 개발자 가이드 (Developer Guide)

본 문서는 PlanCraft Agent 프로젝트의 개발 및 확장을 위한 가이드입니다.

---

## 1. 프로젝트 구조

```
plancraft-agent/
├── app.py                  # Streamlit UI 엔트리포인트
├── api/                    # FastAPI 백엔드 (선택적)
├── agents/                 # AI 에이전트
│   ├── analyzer.py         # 입력 분석
│   ├── structurer.py       # 구조화
│   ├── writer.py           # 초안 작성
│   ├── reviewer.py         # 품질 검토
│   ├── refiner.py          # 개선
│   ├── formatter.py        # 최종 포맷팅
│   ├── supervisor.py       # 전문 에이전트 오케스트레이터
│   └── specialists/        # 전문 에이전트 (Market, BM, Risk 등)
├── graph/                  # LangGraph 워크플로우
│   ├── workflow.py         # StateGraph 정의
│   ├── state.py            # PlanCraftState (TypedDict)
│   ├── interrupt_types.py  # HITL 인터럽트 타입
│   └── interrupt_utils.py  # HITL 유틸리티
├── prompts/                # 프롬프트 템플릿
├── rag/                    # RAG 엔진 (FAISS)
│   ├── documents/          # 불변 가이드 문서
│   └── faiss_manager.py    # 벡터 저장소 관리
├── tools/                  # 외부 도구 (웹 검색 등)
├── ui/                     # UI 컴포넌트
│   ├── components.py       # Streamlit 컴포넌트
│   ├── styles.py           # CSS Design Tokens
│   └── workflow_runner.py  # 워크플로우 실행 로직
├── utils/                  # 유틸리티
│   ├── llm.py              # Azure OpenAI 클라이언트
│   ├── settings.py         # 중앙 설정 (프리셋 포함)
│   ├── schemas.py          # Pydantic 스키마
│   ├── retry.py            # Exponential Backoff
│   └── time_context.py     # 시간 컨텍스트 (연도/분기)
├── tests/                  # 테스트 스위트
└── docs/                   # 문서
```

---

## 2. 개발 환경 설정

### 2.1 필수 요구사항
- Python 3.11+
- Azure OpenAI API 액세스

### 2.2 설치
```bash
git clone <repository-url>
cd plancraft-agent

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2.3 환경변수 (.env)
```env
# 필수
AOAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_API_KEY=your_api_key
AOAI_DEPLOY_GPT4O=gpt-4o
AOAI_DEPLOY_GPT4O_MINI=gpt-4o-mini
AOAI_DEPLOY_EMBED_3_LARGE=text-embedding-3-large

# 선택
TAVILY_API_KEY=...              # 웹 검색
LANGCHAIN_TRACING_V2=true       # LangSmith 추적
LANGCHAIN_PROJECT=PlanCraft     # LangSmith 프로젝트명
CHECKPOINTER_TYPE=memory        # memory|postgres|redis
```

---

## 3. 실행 및 테스트

### 3.1 개발 모드 실행
```bash
streamlit run app.py
```

### 3.2 테스트 실행
```bash
# 전체 테스트
PYTHONPATH=. pytest tests/ -v

# 특정 테스트
PYTHONPATH=. pytest tests/test_workflow_routing.py -v
```

---

## 4. 핵심 패턴

### 4.1 State 관리 (TypedDict)
```python
from graph.state import PlanCraftState, update_state, ensure_dict

def run(state: PlanCraftState) -> PlanCraftState:
    # LLM 호출
    result = llm.invoke(messages)

    # Pydantic → Dict 변환
    result_dict = ensure_dict(result)

    # 불변성 유지하며 상태 업데이트
    return update_state(state, analysis=result_dict)
```

### 4.2 에러 핸들링
```python
from utils.error_handler import handle_node_error

@handle_node_error
def node_function(state: PlanCraftState) -> PlanCraftState:
    # 에러 발생 시 자동으로 state.error에 기록
    pass
```

### 4.3 Self-Reflection 패턴
```python
max_retries = preset.writer_max_retries
for current_try in range(max_retries):
    result = llm.invoke(messages)

    # 자체 검증
    if len(result.sections) < MIN_SECTIONS:
        messages.append({"role": "user", "content": "섹션 부족. 재작성하세요."})
        continue

    break  # 검증 통과
```

### 4.4 HITL (Human-in-the-Loop)
```python
from graph.interrupt_types import InterruptFactory, InterruptType, InterruptOption

# 옵션 선택 인터럽트
payload = InterruptFactory.create(
    InterruptType.OPTION,
    question="방향을 선택하세요",
    options=[
        InterruptOption(title="옵션 A", description="설명"),
        InterruptOption(title="옵션 B", description="설명"),
    ]
)
```

---

## 5. 에이전트 추가/수정

### 5.1 새 에이전트 추가
1. `agents/your_agent.py` 생성
2. `prompts/your_agent_prompt.py` 생성
3. `graph/workflow.py`에 노드 등록
4. 필요시 `utils/schemas.py`에 출력 스키마 추가

### 5.2 프롬프트 수정
- 위치: `prompts/{agent_name}_prompt.py`
- 시스템 프롬프트와 사용자 프롬프트 분리

---

## 6. 품질 프리셋 (Quality Presets)

`utils/settings.py`에서 관리:

| 프리셋 | 모델 | 섹션 수 | 다이어그램 | 재시도 |
|--------|------|---------|-----------|--------|
| fast | gpt-4o-mini | 7개 | 0 | 1회 |
| balanced | gpt-4o-mini | 9개 | 1 | 2회 |
| quality | gpt-4o | 10개 | 1 | 3회 |

---

## 7. 문서 참조

| 문서 | 설명 |
|------|------|
| [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) | 시스템 설계서 |
| [MULTI_AGENT_DIAGRAM.md](MULTI_AGENT_DIAGRAM.md) | 아키텍처 다이어그램 |
| [HITL_GUIDE.md](HITL_GUIDE.md) | HITL 가이드 |

---

## 8. 트러블슈팅

### 8.1 테스트 실패
```bash
# PYTHONPATH 설정 필요
PYTHONPATH=. pytest tests/ -v
```

### 8.2 LLM 타임아웃
```python
# Exponential Backoff 사용
from utils.llm import get_llm_with_retry
llm = get_llm_with_retry(max_retries=3)
```

### 8.3 다이어그램 누락
- `utils/settings.py`에서 `include_diagrams` 값 확인
- Writer 에이전트의 Self-Reflection 로그 확인
