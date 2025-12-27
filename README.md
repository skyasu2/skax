# PlanCraft Agent

AI 기반 **웹/앱 서비스 기획서** 자동 생성 Multi-Agent 시스템

## 📋 개요

PlanCraft Agent는 사용자의 아이디어를 입력받아 자동으로 **웹/앱 서비스 기획서**를 생성해주는 AI 서비스입니다.
6개의 전문 Agent가 협업하여 분석 → 구조 설계 → 내용 작성 → 검토 → 개선 → 요약의 과정을 거쳐 완성도 높은 기획서를 만들어냅니다.

## 🚀 주요 기능

- **Robust Multi-Agent System**: 6개 전문 Agent가 협업하는 모듈형 아키텍처
- **Type-Safe State Management**: **Pydantic BaseModel**을 사용한 강력한 타입 검증 및 상태 관리 (New!)
- **Human-in-the-loop**: 불명확한 요구사항에 대해 사용자에게 역으로 질문하여 방향성을 조율
- **MCP (Model Context Protocol)**: 표준 프로토콜 기반 외부 도구 연동 (Tavily 검색, URL Fetch)
- **Automated Quality Control**: Reviewer → Refiner 루프를 통한 품질 자동 개선
- **Fault Tolerance**: 각 단계별 Fallback 로직으로 LLM 오류 시에도 중단 없는 서비스 제공
- **RAG Integration**: 내부 가이드 문서를 참조하여 회사/팀 표준에 맞는 기획서 작성

## 🛠 기술 스택

- **Core**: Python 3.10+, LangChain, **LangGraph**
- **LLM**: Azure OpenAI (gpt-4o, gpt-4o-mini)
- **State Management**: **Pydantic** (TypedDict를 대체하여 타입 안정성 확보)
- **Test**: **Interactive Unit Testing** (Dev Tools in Sidebar)
- **Vector DB**: FAISS (Local)
- **Embedding**: text-embedding-3-large
- **MCP Servers**: mcp-server-fetch (URL), tavily-mcp (AI 검색)
- **UI**: Streamlit

## 📁 프로젝트 구조

```
├── app.py                    # Streamlit 메인 앱 (UI Layer)
├── requirements.txt          # 의존성 패키지
├── agents/                   # [Agent Layer] 단일 책임 원칙 준수
│   ├── analyzer.py           # 요구사항 분석 및 불분명시 질문 생성
│   ├── structurer.py         # 기획서 목차/구조 설계
│   ├── writer.py             # 섹션별 상세 내용 작성 (초안)
│   ├── reviewer.py           # 품질 검토 및 개선점 도출 (Judge)
│   ├── refiner.py            # 피드백 반영 및 최종본 완성
│   └── formatter.py          # 사용자 친화적 요약 생성
├── graph/                    # [Workflow Layer]
│   ├── state.py              # Pydantic 기반 상태 모델 (PlanCraftState)
│   └── workflow.py           # LangGraph StateGraph 정의
├── rag/                      # [RAG Layer]
│   ├── documents/            # 지식 베이스 (가이드 문서)
│   ├── vectorstore.py        # FAISS 관리
│   └── retriever.py          # 맥락 기반 검색
├── tools/                      # [MCP Layer - Model Context Protocol]
│   ├── mcp_client.py         # MCP 통합 클라이언트 (Fetch + Tavily)
│   ├── web_search.py         # 조건부 검색 로직
│   └── web_client.py         # URL 콘텐츠 Fetcher (Fallback)
├── utils/                    # [Common Utilities]
│   ├── config.py             # 환경 변수 및 설정 검증
│   ├── llm.py                # LLM 인스턴스 팩토리
│   └── schemas.py            # 입출력 Pydantic 스키마 정의
├── tests/                    # [Test Layer]
│   └── test_agents.py        # pytest 단위 테스트
└── docs/                     # [Documentation]
    ├── architecture.md       # 시스템 아키텍처 문서
    └── agent-design.md       # Agent 설계 명세
```

## ⚙️ 설치 및 실행

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env.example`을 복사하여 `.env.local` 파일 생성:
```bash
cp .env.example .env.local
```

`.env.local` 필수 설정:
```ini
AOAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_API_KEY=your_api_key_here
AOAI_DEPLOY_GPT4O_MINI=gpt-4o-mini
AOAI_DEPLOY_GPT4O=gpt-4o
AOAI_DEPLOY_EMBED_3_LARGE=text-embedding-3-large
# LangSmith (Optional - 모니터링용)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langchain_api_key

# MCP (Model Context Protocol)
MCP_ENABLED=true
TAVILY_API_KEY=your_tavily_api_key
```

### 3. RAG 벡터스토어 초기화
```bash
python -c "from rag.vectorstore import init_vectorstore; init_vectorstore()"
```

### 4. 앱 실행
```bash
streamlit run app.py
```

## 📖 사용 시나리오

1. **단순 요청**: "점심 메뉴 추천 앱 기획해줘"
    - 내부 지식으로 즉시 분석 → 구조 설계 → 작성 → 완성
2. **복합 요청**: "최신 AI 트렌드를 반영한 가계부 앱"
    - "최신 AI 트렌드" 키워드 감지 → **웹 검색 수행** → 정보 반영하여 기획
3. **불명확한 요청**: "앱 하나 만들어줘"
    - Analyzer가 정보 부족 판단 → "어떤 종류의 앱인가요? (예: 커뮤니티, 커머스 등)" **역질문(Human-in-the-loop)** → 사용자 답변 후 진행

## 🤖 Agent 상세 역할

| Agent | 역할 | 구현 특징 |
|-------|------|-----------|
| **Analyzer** | 입력 분석, 검색 필요 여부 판단 | `AnalysisResult` 스키마로 구조화된 분석, 필요 시 `options` 생성 |
| **Structurer** | 기획서 섹션 구조(목차) 설계 | 논리적인 흐름(Why-What-How) 설계 |
| **Writer** | 각 섹션별 본문 작성 | 구조에 맞춰 상세 내용 생성 (Markdown) |
| **Reviewer** | 품질 검토 (Pass/Revise/Fail) | 명확한 기준에 따른 채점 및 `action_items` 도출 |
| **Refiner** | 피드백 반영 및 개선 | Reviewer의 지적 사항을 반영하여 최종본 완성 |
| **Formatter** | 최종 요약 및 포맷팅 | Streamlit 채팅 UI에 최적화된 메시지 변환 |

## 🌐 웹 검색 동작 조건

### 웹 검색이 수행되는 경우 ✅

| 조건 | 예시 입력 |
|------|-----------|
| **최신 정보 키워드** | "최신 AI 트렌드", "2025년 시장 현황" |
| **외부 시장 정보** | "경쟁사 분석", "시장 규모", "업계 동향" |
| **URL 직접 제공** | "https://example.com 참고해서 기획서 작성" |

### 웹 검색이 수행되지 않는 경우 ❌

| 조건 | 이유 |
|------|------|
| **일반 기획 요청** | "점심 메뉴 추천 앱" → 내부 지식으로 충분 |
| **RAG 컨텍스트 충분** | 이미 관련 문서가 검색됨 |

## 🔮 Future Roadmap

실제 프로덕션 레벨 도약을 위한 향후 고도화 계획입니다:

- **Automated CI/CD**: GitHub Actions를 활용한 파이프라인 자동화 (현재는 UI 기반 테스트 제공)
- **Observability**: **LangSmith** 연동을 통한 Trace 추적 및 데이터셋 기반 성능 평가
- **Advanced Routing**: `RunnableBranch` 패턴을 적용한 동적 라우팅 및 확장성 확보
- **Feedback Loop**: 사용자 피드백 데이터를 저장하고 학습에 활용하는 파이프라인 구축

## 📝 License

MIT License
