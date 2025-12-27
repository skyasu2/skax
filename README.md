# PlanCraft Agent

AI 기반 **웹/앱 서비스 기획서** 자동 생성 Multi-Agent 시스템

## 📋 개요

PlanCraft Agent는 사용자의 아이디어를 입력받아 자동으로 **웹/앱 서비스 기획서**를 생성해주는 AI 서비스입니다.
6개의 전문 Agent가 협업하여 분석 → 구조 설계 → 내용 작성 → 검토 → 개선 → 요약의 과정을 거쳐 완성도 높은 기획서를 만들어냅니다.

## 🚀 주요 기능

- **Multi-Agent 시스템**: 6개 Agent 협업 (Analyzer, Structurer, Writer, Reviewer, Refiner, Formatter)
- **자율 판단 기획**: 질문 없이 RAG/웹 검색을 활용하여 베스트 프랙티스로 기획서 작성
- **자동 개선**: Reviewer 피드백을 Refiner가 직접 반영하여 완성본 출력
- **사용자 친화적 요약**: Formatter가 채팅에 적합한 요약 생성
- **RAG 기반 품질 향상**: 기획서 작성 가이드 문서를 참조
- **조건부 웹 검색**: 최신 정보 필요 시에만 DuckDuckGo 검색 수행
- **LangGraph 워크플로우**: 조건부 분기와 순차 실행을 지원하는 유연한 파이프라인
- **Streamlit UI**: 채팅 스타일의 직관적인 웹 인터페이스

## 🛠 기술 스택

- **LLM**: Azure OpenAI (gpt-4o, gpt-4o-mini)
- **Framework**: LangChain, LangGraph
- **Vector DB**: FAISS
- **UI**: Streamlit
- **Embedding**: text-embedding-3-large
- **Web Search**: DuckDuckGo

## 📁 프로젝트 구조

```
├── app.py                    # Streamlit 메인 앱
├── requirements.txt          # 의존성 패키지
├── agents/                   # Agent 정의
│   ├── analyzer.py           # 입력 분석 (질문 없이 자율 판단)
│   ├── structurer.py         # 구조 설계
│   ├── writer.py             # 내용 작성
│   ├── reviewer.py           # 검토 피드백
│   ├── refiner.py            # 피드백 반영 개선
│   └── formatter.py          # 사용자 친화적 요약
├── prompts/                  # 프롬프트 템플릿
│   ├── analyzer_prompt.py
│   ├── structurer_prompt.py
│   ├── writer_prompt.py
│   ├── reviewer_prompt.py
│   ├── refiner_prompt.py
│   └── formatter_prompt.py
├── rag/                      # RAG 관련
│   ├── documents/            # RAG용 가이드 문서
│   ├── vectorstore.py        # FAISS 벡터스토어
│   └── retriever.py          # 검색 로직
├── graph/                    # LangGraph 워크플로우
│   ├── state.py              # 상태 정의
│   └── workflow.py           # 그래프 정의
├── mcp/                      # 웹 조회
│   ├── web_search.py         # 조건부 DuckDuckGo 검색
│   ├── web_client.py         # URL 콘텐츠 fetch
│   └── file_utils.py         # 파일 저장 유틸리티
├── utils/                    # 유틸리티
│   ├── config.py             # 설정 로드
│   ├── llm.py                # Azure OpenAI 클라이언트
│   └── schemas.py            # Pydantic 스키마
└── docs/                     # 문서
    └── architecture.md       # 아키텍처 설명
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

`.env.local` 파일을 열어 실제 API 키 입력:
```
AOAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_API_KEY=your_api_key_here
AOAI_DEPLOY_GPT4O_MINI=gpt-4o-mini
AOAI_DEPLOY_GPT4O=gpt-4o
AOAI_DEPLOY_EMBED_3_LARGE=text-embedding-3-large
```

### 3. RAG 벡터스토어 초기화 (최초 1회)
```bash
python -c "from rag.vectorstore import init_vectorstore; init_vectorstore()"
```

### 4. Streamlit 실행
```bash
streamlit run app.py
```

## 📖 사용 방법

1. 웹 브라우저에서 Streamlit 앱 접속
2. 아이디어나 기획 요청 입력 (예: "점심 메뉴 추천 앱")
3. AI Agent가 자동으로 기획서 생성
4. 생성된 기획서 확인 및 다운로드

## 🔄 워크플로우

```
┌─────────────┐
│   START     │
└──────┬──────┘
       ▼
┌─────────────┐
│  retrieve   │  ← RAG 검색
└──────┬──────┘
       ▼
┌─────────────┐
│ fetch_web   │  ← 조건부 웹 검색
└──────┬──────┘
       ▼
┌─────────────┐     need_more_info=True    ┌─────────┐
│   analyze   │ ─────────────────────────▶ │   END   │
└──────┬──────┘                             └─────────┘
       │ need_more_info=False
       ▼
┌─────────────┐
│  structure  │  ← 기획서 구조 설계
└──────┬──────┘
       ▼
┌─────────────┐
│    write    │  ← 내용 작성
└──────┬──────┘
       ▼
┌─────────────┐
│   review    │  ← 검토 및 피드백
└──────┬──────┘
       ▼
┌─────────────┐
│   refine    │  ← 피드백 반영 개선
└──────┬──────┘
       ▼
┌─────────────┐
│   format    │  ← 사용자 친화적 요약
└──────┬──────┘
       ▼
┌─────────────┐
│     END     │
└─────────────┘
```

## 🤖 Agent 역할

| Agent | 역할 | 출력 |
|-------|------|------|
| **Analyzer** | 입력 분석, 자율 판단으로 기획 방향 결정 | `analysis` |
| **Structurer** | 기획서 섹션 구조 설계 | `structure` |
| **Writer** | 섹션별 내용 작성 | `draft` |
| **Reviewer** | 검토 및 개선점 도출 | `review` |
| **Refiner** | 개선점 직접 반영하여 완성본 생성 | `final_output` |
| **Formatter** | 채팅용 요약 메시지 생성 | `chat_summary` |

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

## 📝 License

MIT License
