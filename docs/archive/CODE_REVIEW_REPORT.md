# PlanCraft Agent 코드 베이스 리뷰 리포트

**작성일**: 2026-01-03
**리뷰어**: Antigravity Assistant

---

## 1. 개요
본 문서는 PlanCraft Agent 프로젝트의 코드 베이스를 심층 분석한 결과를 담고 있습니다. 프로젝트의 아키텍처, 주요 모듈(Agents, Workflow), 데이터 구조, 그리고 코드 품질 전반을 검토하였으며, 이를 바탕으로 개선이 필요한 영역과 구체적인 제안을 제시합니다.

## 2. 전체 아키텍처 및 구조
프로젝트는 **Streamlit(Frontend) + FastAPI(Backend API) + LangGraph(Orchestration)** 기반의 모던 AI 에이전트 아키텍처를 따르고 있습니다. 명확한 관심사 분리(SoC)가 이루어져 있으며, 특히 확장성과 유지보수성을 고려한 구성을 갖추고 있습니다.

### 강점
*   **모듈화**: `agents/`, `graph/`, `api/`, `ui/` 등 역할별로 디렉토리가 잘 구분되어 있습니다.
*   **LangGraph 활용**: 최신 LangGraph v0.2+ 패턴(StateGraph, TypedDict State, Conditional Edges)을 충실히 따르고 있습니다.
*   **상태 관리**: `graph/state.py`에서 Input, Output, Internal State를 명확히 분리하여 API 설계를 견고하게 했습니다.
*   **문서화**: `docs/` 내의 시스템 설계 및 사용자 가이드가 매우 충실합니다.

### 개선 가능 영역
*   **스레드 관리**: `app.py` 내에서 `threading`으로 FastAPI 서버를 구동하는 방식은 개발 편의성은 높으나, 프로덕션 배포 시에는 프로세스 분리가 필요할 수 있습니다.
*   **의존성 관리**: `agents` 모듈 간의 암시적 의존성이 일부 존재하여, 테스트 시 모킹(Mocking)이 까다로울 수 있습니다.

---

## 3. 주요 모듈별 상세 리뷰

### 3.1 Agents (`agents/`)

#### **Analyzer (`analyzer.py`)**
*   **기능**: 사용자 입력 및 파일 내용을 분석하여 구조화된 데이터 생성.
*   **강점**: 입력 길이에 따른 Fast Track / HITL 분기 처리가 UX 측면에서 우수합니다.
*   **제안**: `settings` 객체 활용이 함수 내부에 산재해 있어, 설정 의존성을 주입(DI) 받는 형태로 리팩토링하면 테스트가 더 용이할 것입니다.

#### **Structurer (`structurer.py`)**
*   **기능**: 기획서 목차 설계.
*   **강점**: 프리셋(`fast`, `balanced`, `quality`)에 따른 동적 파라미터(섹션 수 등) 조정 로직이 잘 구현됨. Self-Reflection 루프를 통한 품질 보장 로직이 돋보입니다.
*   **제안**: `MAX_RETRIES` 로직이 코드 내에 직접 구현되어 있는데, LangGraph의 `Node Retry Policy` 기능을 활용하면 코드를 더 간결하게 만들 수 있습니다.

#### **Writer (`writer.py`)**
*   **기능**: 섹션별 상세 콘텐츠 작성.
*   **강점**: 웹 검색, 멀티 에이전트 협업(Supervisor), 시각적 요소(Mermaid/Chart) 통합 등 기능이 풍부함.
*   **약점**: 한 파일 내에 너무 많은 책임(검색, Supervisor 실행, 검증, 프롬프트 구성)이 집중되어 있어 복잡도가 높습니다 (`600+ lines`).
*   **제안**: `WriterHelper` 클래스나 별도 모듈(`writer_utils.py`)로 웹 검색 실행기, 검증 로직, 시각화 지침 생성기 등을 분리하는 **리팩토링이 시급**합니다.

#### **Supervisor (`supervisor.py`)**
*   **기능**: 전문 에이전트 오케스트레이션.
*   **강점**: `Rule-based`와 `LLM-based` 라우팅을 혼합하여 효율성과 유연성을 모두 잡았습니다. 실행 통계(`ExecutionStats`)를 상세히 추적하는 코드는 운영 관제에 매우 유용합니다.
*   **제안**: `ThreadPoolExecutor`를 사용한 병렬 실행은 좋으나, LangGraph의 `Send` API(v0.2 신기능)를 활용하면 Map-Reduce 패턴을 더 네이티브하게 구현할 수 있습니다.

### 3.2 Graph Workflow (`graph/`)

#### **Workflow (`workflow.py`)**
*   **강점**: `TypedDict` 기반의 엄격한 타입 체크, `Command` 타입 활용 시도 등 최신 베스트 프랙티스를 적용하려 노력했습니다.
*   **제안**: `RunnableBranch`와 `Conditional Edges`가 혼용되고 있습니다. 가독성을 위해 `add_conditional_edges` 패턴으로 통일하는 것을 권장합니다.

#### **State (`state.py`)**
*   **강점**: `PlanCraftState` 정의가 매우 상세하며, `update_state` 헬퍼 함수를 통해 불변성을 보장하는 방식이 인상적입니다.
*   **제안**: 상태 객체가 커짐에 따라(Large State), 필요한 데이터만 부분적으로 전달하는 `Reducer` 패턴 적용을 고려해볼 만합니다.

---

## 4. 코드 품질 및 기타

*   **에러 핸들링**: `utils/error_handler.py` 및 데코레이터(`@handle_node_error`)를 일관되게 적용하여 안정성을 확보했습니다.
*   **로깅**: `FileLogger` 시스템이 잘 구축되어 있으나, 로그 파일 로테이션 정책이나 중앙 집중식 로깅 연동 고려가 필요해 보입니다.
*   **테스트**: 테스트 코드가 풍부하지만(`300+ tests`), 통합 테스트(E2E) 비중을 높여 실제 워크플로우 완주 확률을 검증해야 합니다.

## 5. 종합 제안 및 우선순위

### 🚨 우선순위 1: Writer 에이전트 리팩토링
*   **이유**: `writer.py`의 복잡도가 높아 유지보수가 어렵고 버그 발생 가능성이 높습니다.
*   **액션**: `WebSearchExecuter`, `DraftValidator`, `VisualInstructionGenerator` 등으로 로직 분리.

### 🚨 우선순위 2: LangGraph 기능 최신화
*   **이유**: `Command` 객체 및 `Send` API 등 최신 기능을 활용하여 코드 간결성 및 성능 향상.
*   **액션**: `supervisor.py` 및 `workflow.py`의 분기/병렬 처리 로직 업데이트.

### ⚠️ 우선순위 3: 테스트 커버리지 보완
*   **이유**: 복잡한 HITL 시나리오에 대한 자동화 테스트가 부족할 수 있음.
*   **액션**: 상태 모킹(Mock State)을 활용한 시나리오별 단위 테스트 추가.

---
**총평**: PlanCraft Agent는 상용 수준의 완성도를 목표로 잘 설계된 프로젝트입니다. 제안된 리팩토링과 최적화를 수행한다면 더욱 견고하고 확장 가능한 시스템이 될 것입니다.
