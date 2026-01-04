# AI Bootcamp Capstone Project: PlanCraft Agent

**프로젝트명**: Multi-Agent Orchestration & HITL 기반 기획 어시스턴트
**작성일**: 2026.01.02

---

## 1. 프로젝트 개요

### 1.1 배경 및 문제 정의
비즈니스 기획서는 시장 분석, BM 설계, 기술 검토 등 여러 영역의 전문 지식을 필요로 한다. 단일 LLM은 단순 질의응답에는 적합하나, 논리적 구조화와 다각적 분석이 요구되는 기획서 작성에서는 일관성 유지에 한계가 있다.

### 1.2 솔루션
본 프로젝트는 AI Bootcamp 커리큘럼의 핵심 기술을 적용하여 Multi-Agent System을 구현했다.
- **Supervisor**: 전체 워크플로우 조율
- **Specialist Agents**: 영역별 전담 분석 (시장, BM, 리스크, 기술)
- **Human-in-the-Loop**: 사용자 상호작용 지원

---

## 2. 커리큘럼 기술 적용

AI Bootcamp 6개 핵심 모듈의 프로젝트 적용 내역을 기술한다.

### 2.1 LLM Fundamentals
- **학습 내용**: Structured Output, Function Calling
- **적용 내용**:
  - 모든 에이전트 출력을 Pydantic Model로 정의하여 타입 안전성 확보
  - `ensure_dict()` 유틸리티로 Pydantic↔Dict 변환 처리

### 2.2 Prompt Engineering
- **학습 내용**: 프롬프트 설계, 최적화 기법
- **적용 내용**:
  - Persona Pattern: 에이전트별 페르소나 및 지시사항 정의
  - Chain-of-Thought: 논리적 구조 설계를 위한 단계별 사고 유도

### 2.3 Azure OpenAI & LangChain
- **학습 내용**: LangGraph, LangChain 활용
- **적용 내용**:
  - LangGraph StateGraph로 순환/분기 가능한 Stateful Workflow 구현
  - Checkpointing: 상태 저장 및 중단 시점 재개 기능

### 2.4 RAG (Retrieval-Augmented Generation)
- **학습 내용**: Vector DB, AI 검색 최적화
- **적용 내용**:
  - `rag/` 모듈: 기획서 양식, 가이드라인 문서 벡터화 저장
  - Writer Agent가 RAG 검색 결과를 참조하여 초안 작성

### 2.5 서비스 개발 및 패키징
- **학습 내용**: Streamlit UI, FastAPI 백엔드 분리
- **적용 내용**:
  - Streamlit: 채팅 UI, Mermaid 다이어그램, 실시간 상태 표시
  - FastAPI: UI와 Agent 로직 분리, REST API 제공

### 2.6 MCP / A2A (Agent-to-Agent)
- **학습 내용**: Agent 간 연결, MCP 개념
- **적용 내용**:
  - Supervisor Orchestration: Plan-and-Execute 패턴으로 에이전트 동적 할당
  - Tool-based Handoff: Specialist를 Tool 형태로 래핑하여 호출

---

## 3. 아키텍처 특징

### 3.1 Dynamic Supervisor (Factory Pattern)
- **특징**: 에이전트 추가 시 코드 수정 불필요 (OCP 준수)
- **구현**: `AGENT_REGISTRY` 설정 기반 런타임 동적 로딩

### 3.2 Safe Human-in-the-Loop (HITL)
- **특징**: Side-effect 중복 실행 방지
- **구현**: `interrupt()` 전후 로직 분리, Semantic Interrupt ID 사용

### 3.3 Quality Presets
- **특징**: 용도별 리소스 최적화
  - Fast: `gpt-4o-mini` (속도 중심)
  - Quality: `gpt-4o` + 심층 분석 (품질 중심)

### 3.4 FastAPI Backend 분리
- **특징**: UI와 Agent 로직 분리
- **구현**: `/api/v1/workflow/run`, `/api/v1/workflow/resume` 엔드포인트 제공

---

## 4. 트러블슈팅

### 4.1 순환 의존성 해결
- **문제**: 에이전트 간 상호 참조로 DAG 생성 시 무한 루프 가능성
- **해결**: DFS 기반 Cycle Detection 추가, 순환 감지 시 순차 실행으로 Fallback

### 4.2 동적 분기 상태 관리
- **문제**: 사용자 입력에 따른 워크플로우 경로 변경 시 상태 관리 복잡도 증가
- **해결**: `PlanCraftState` TypedDict 정의, `update_state()` 헬퍼로 불변성 유지

---

## 5. 결론

본 프로젝트는 AI Bootcamp 학습 내용을 종합 적용하여 Multi-Agent 기반 기획서 생성 시스템을 구현했다.

- **10개 에이전트** 협업 구조 (Supervisor + 6 Specialists + 3 Core Agents)
- **HITL 패턴** 적용으로 사용자 개입 지원
- **RAG + Web Search** 하이브리드 컨텍스트 활용
- **FastAPI/Streamlit** 기반 서비스 아키텍처

---

## 6. 유지보수 및 리팩토링 (2025.01.03 추가)

지속적인 서비스 안정성과 코드 품질 향상을 위해 핵심 모듈에 대한 리팩토링을 수행했다.

### 6.1 Writer Agent 모듈화
- **이슈**: `writer.py`가 웹 검색, 전문가 에이전트 연동, 시각화 가이드 생성 등 과도한 책임(High Complexity)을 가지고 있어 유지보수가 어려웠음.
- **해결**:
  - `agents/writer_helpers.py` 신설: 헬퍼 함수들을 별도 모듈로 분리 (SoC 준수).
  - `writer.py`: 핵심 워크플로우 로직과 상태 관리로 역할 축소, 코드 가독성 향상.

### 6.2 Workflow 최신화 점검
- **현황**: LangGraph 업그레이드 과정에서 레거시 패턴(`RunnableBranch`) 잔존 가능성 확인.
- **조치**: 코드 베이스 전수 조사를 통해 레거시 패턴이 존재하지 않음을 확인. 현재 `Conditional Edges` 및 `Sub-graph` 패턴이 올바르게 적용되어 있음.

### 6.3 안전장치(Tests) 확충
- **조치**: 주요 리팩토링 대상인 Writer Agent의 정상 동작을 검증하는 단위 테스트(`tests/verify_writer_refactor.py`) 추가.
- **결과**: Import 경로 문제 해결 및 Mocking 테스트 통과로 리팩토링 안전성 확보.

### 6.4 Supervisor 성능 최적화 (2025.01.03 심화)
- **개선 목표**: 병렬 실행 시 과도한 리소스 점유 방지 및 무한 대기(Hanging) 방지.
- **적용 내용**:
  - `ThreadPoolExecutor`에 `max_workers` 설정 적용 (기본 5개로 제한).
  - 개별 에이전트 실행에 `timeout` (기본 60초) 적용하여 장애 발생 시 즉시 Failover.
  - 비동기 워크플로우 지원을 위한 `arun()` 래퍼 메서드 추가.
  - `utils/settings.py`에 관련 설정(`MAX_PARALLEL_AGENTS`, `AGENT_TIMEOUT_SEC`) 추가 및 환경변수 연동.
