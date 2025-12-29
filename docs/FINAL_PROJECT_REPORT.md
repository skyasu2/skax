# 🎓 End-to-End AI Agent 서비스 개발 과제 결과 보고서

## 1. 프로젝트 개요 (Overview)
- **프로젝트명**: PlanCraft Agent (AI 기반 기획서 작성 및 컨설팅 서비스)
- **한줄 소개**: 사용자의 아이디어를 분석하여 전문적인 IT 서비스 기획서(PRD)를 작성, 검토, 개선하는 Multi-Agent 시스템
- **개발 목적**: 기획 초기 단계의 막막함 해소 및 표준화된 기획 문서 자동화
- **핵심 가치**: 10년차 기획자 페르소나의 AI가 RAG(가이드)와 Web(최신 트렌드)를 결합하여 실전 수준의 문서 제공

---

## 2. 아키텍처 및 기술적 구현 (Technical Implementation)

### 2.1 Agent 구조 설계 (LangGraph 기반 Multi-Agent)
본 프로젝트는 단일 Agent가 아닌, **책임이 분리된 5개의 전문 Agent**가 협업하는 구조입니다.
1. **Analyzer (분석가)**: 사용자 요청 의도 파악 및 부족한 정보 식별 (ReAct)
2. **Structurer (설계자)**: 기획서 목차 및 논리적 구조 설계
3. **Writer (작가)**: RAG 가이드와 웹 정보를 결합하여 본문 작성
4. **Reviewer (검토자)**: 작성된 기획서 평가 (점수화) 및 피드백 생성
5. **Refiner (개선자)**: 피드백 기반으로 기획서 수정 및 포맷팅

### 2.2 RAG (Retrieval-Augmented Generation) 구현
- **Vector DB**: FAISS (로컬 임베딩 저장소)
- **Source**: `docs/guidelines/` 내의 기획 가이드 문서 인덱싱
- **Retrieval**: `retrieve_context` 노드에서 사용자 쿼리와 연관된 가이드 추출 → Writer/Analyzer에 주입

### 2.3 고급 기술 요소 (Advanced Features)
- **Structured Output**: 모든 Agent는 Pydantic 모델(`DraftResult`, `ReviewResult` 등)을 통해 정형화된 JSON 출력 보장
- **Conditional Branching (동적 라우팅)**:
  - Review 점수가 낮을 경우(`FAIL`) → **Refiner 루프** 또는 **Analyzer 재분석**으로 자동 회귀
  - 사용자 입력 불충분 시 → **Human Interrupt**를 통해 추가 정보 요청
- **MCP (Model Context Protocol)**:
  - `tools/mcp_client.py`를 통해 외부 MCP 서버(Web Search, Filesystem 등)와 연통 가능한 구조 설계
  - (Fallback: `duckduckgo-search` 등 로컬 도구 자동 전환 구현)

---

## 3. 과제 요구사항 충족 여부 (Compliance Matrix)

| 구분 | 필수 요건 | 구현 내용 및 증빙 파일 | 충족 여부 |
|------|-----------|------------------------|-----------|
| **Prompt** | 역할 기반 설계 | `prompts/` 내 5개 분야별 전용 프롬프트 및 CoT 적용 | ✅ |
| **Agent** | Multi-Agent | Analyzer-Writer-Reviewer 루프 구조 구현 (`graph/workflow.py`) | ✅ |
| **Agent** | Memory 활용 | LangGraph `checkpointer` 및 `Thread-ID`로 전체 대화/상태 영구 보존 | ✅ |
| **Agent** | Tool Calling | `analyzer_llm.with_structured_output()` 등 Function Calling 기반 제어 | ✅ |
| **Agent** | ReAct 기반 실행 | `should_search_web` 도구에서 LLM이 검색 필요성 판단(Reasoning) 후 쿼리 실행(Action) (`tools/web_search.py`) | ✅ |
| **RAG** | Vector DB 구성 | `rag/` 모듈 내 FAISS 인덱싱 및 Retriever 구현 | ✅ | (7번 항목으로 이동)
| **Service** | UI 패키징 | Streamlit 기반 채팅/시각화/히스토리 UI 구현 (`app.py`, `ui/`) | ✅ |
| **Advanced** | Structured Output | `with_structured_output` 사용하여 LLM 응답 정형화 (`utils/schemas.py`) | ✅ |
| **Advanced** | A2A 협업 | Reviewer 피드백을 Refiner/Analyzer가 받아 수정하는 순환 구조 | ✅ |
| **Advanced** | MCP | MCP 클라이언트 구현 (`tools/mcp_client.py`) | ✅ |

---

## 4. 서비스 워크플로우 (End-to-End)
1. **Input**: 사용자가 "배달 앱 기획해줘" 입력
2. **Analysis**: Analyzer가 요구사항 분석 (필요시 역제안/추가질문)
3. **Context**: RAG(기획표준) + Web(시장조사) 병렬 수집
4. **Drafting**: Structurer가 목차 잡고 Writer가 초안 작성
5. **Evaluation**: Reviewer가 10점 만점 평가
   - 점수 미달 시: Refiner가 자동 개선 (Loop)
   - 점수 충족 시: 최종 Markdown 포맷팅
6. **Output**: Streamlit UI에 기획서 렌더링 및 다운로드 제공

---

## 5. 결론 및 기대효과
본 서비스는 단순한 LLM 래퍼가 아니라, **실제 업무 프로세스(분석-작성-검토-수정)**를 모방한 Agentic Workflow를 구현했습니다. LangGraph의 주도적인 제어 흐름과 Streamlit의 편리한 UI를 결합하여, 실무에서도 즉시 활용 가능한 수준의 완성도를 확보했습니다.
