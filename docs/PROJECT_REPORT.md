# 🎓 AI Bootcamp Capstone Project: PlanCraft Agent

**프로젝트명**: Multi-Agent Orchestration & HITL 기반의 지능형 기획 어시스턴트
**작성일**: 2026.01.02

---

## 1. 🌟 프로젝트 개요 (Overview)

### 1.1 배경 및 문제 정의
현대의 비즈니스 기획은 시장 분석, BM 설계, 기술 검토 등 다양한 영역의 전문 지식을 요구합니다. 단일 LLM(ChatGPT 등)은 단순 질의응답에는 강하지만, **긴 호흡의 논리적 구조화**와 **다각적 분석**이 필요한 '기획서 작성' 업무에서는 전문성과 일관성이 부족한 한계를 보입니다.

### 1.2 솔루션
본 프로젝트는 **AI Bootcamp**에서 학습한 핵심 기술을 집약하여, 인간 기획자처럼 사고하고 협업하는 **Multi-Agent System**을 구축했습니다.
**Supervisor**가 전체 과정을 조율하고, **Specialist Agents**가 각 영역을 전담하며, **Human-in-the-Loop**를 통해 사용자와 상호작용하는 차세대 Agent 시스템입니다.

---

## 2. 📚 커리큘럼 기반 기술 적용 (Tech Stack Mapping)

AI Bootcamp의 6대 핵심 모듈을 실제 프로젝트 코드에 어떻게 적용했는지 상세히 기술합니다.

### 2.1 LLM Fundamentals
*   **학습 내용**: Structured Output, Function Calling
*   **프로젝트 적용**:
    *   모든 에이전트의 출력을 **Pydantic Model**(`RoutingDecision`, `StructureResult`)로 강제하여, LLM의 환각(Hallucination)을 제어하고 다운스트림 로직의 안정성을 확보했습니다.
    *   `ensure_dict` 유틸리티를 구현하여 객체와 딕셔너리 간의 타입 불일치 문제를 해결했습니다.

### 2.2 Prompt Engineering
*   **학습 내용**: 프롬프트 설계, 최적화 기법
*   **프로젝트 적용**:
    *   **Persona Pattern**: Market, BM, Risk 등 6가지 에이전트별로 구체적인 페르소나와 지시사항(Instruction)을 부여했습니다.
    *   **Chain-of-Thought**: "생각한 뒤 답변하라"는 지시를 통해 복잡한 기획 구조를 논리적으로 설계하도록 유도했습니다.

### 2.3 Azure OpenAI & LangChain
*   **학습 내용**: LangGraph 에이전트 시스템, LangChain 활용
*   **프로젝트 적용 (핵심)**:
    *   단순 Chain이 아닌 **LangGraph**를 도입하여, 순환(Cycle)과 분기(Branching)가 가능한 **Stateful Workflow**를 구축했습니다.
    *   **Checkpointing**: 대화의 상태를 지속적으로 저장하여, 중단된 시점부터 정확하게 재개(Resume)할 수 있는 기능을 구현했습니다.

### 2.4 RAG (Retrieval-Augmented Generation)
*   **학습 내용**: Vector DB, AI 검색 최적화
*   **프로젝트 적용**:
    *   `rag/` 모듈을 통해 기획서 양식, 사내 가이드라인 문서를 벡터화하여 저장했습니다.
    *   Writer Agent가 초안 작성 시 RAG를 통해 **참조 문서를 검색**함으로써, 일반적인 내용이 아닌 도메인 특화된 고품질 기획서를 생성합니다.

### 2.5 서비스 개발 및 패키징
*   **학습 내용**: Streamlit UI 구축, 서비스 운영
*   **프로젝트 적용**:
    *   **Streamlit**을 활용하여 채팅 인터페이스뿐만 아니라, **Mermaid 다이어그램 시각화**, **실시간 상태 타임라인(Timeline)** 등을 포함한 rich UI를 개발했습니다.
    *   설정(`settings.py`)과 UI 컴포넌트(`ui/`)를 모듈화하여 유지보수성을 높였습니다.

### 2.6 MCP / A2A (Agent-to-Agent)
*   **학습 내용**: Agent 간 연결, MCP 개념
*   **프로젝트 적용**:
    *   **Supervisor Orchestration**: 중앙 감독관(Supervisor)이 하위 에이전트들에게 작업을 동적으로 할당하는 **Plan-and-Execute** 패턴을 구현했습니다.
    *   **Tool-based Handoff**: 각 전문 에이전트를 도구(Tool) 형태로 래핑하여, Supervisor가 상황에 따라 필요한 도구를 선택 호출하는 **A2A 협업 구조**를 완성했습니다.

---

## 3. 🏗️ 아키텍처 혁신 (Architectural Innovation)

### 3.1 Dynamic Supervisor with Factory Pattern (OCP)
*   **혁신점**: 새로운 에이전트 추가 시 코드를 수정할 필요가 없는 **개방-폐쇄 원칙(OCP)** 구조를 구현했습니다.
*   **구현**: `AGENT_REGISTRY`에 설정만 추가하면, Supervisor가 런타임에 동적으로 에이전트를 로드하고 실행 계획에 반영합니다.

### 3.2 Safe Human-in-the-Loop (HITL)
*   **혁신점**: 인간 개입 시 발생할 수 있는 **Side-effect 중복 실행 문제**를 원천 차단했습니다.
*   **구현**: `interrupt` 함수 호출 전후로 로직을 엄격히 분리하고, **Semantic Interrupt ID**를 사용하여 재개(Resume) 시점의 안전성을 보장했습니다.

### 3.3 Quality Presets & Resource Strategy
*   **혁신점**: 사용자의 니즈에 따라 AI 리소스를 최적화했습니다.
    *   ⚡ **Fast Mode**: `gpt-4o-mini` (속도/비용 효율)
    *   💎 **Quality Mode**: `gpt-4o` + 심층 분석 + 다이어그램 생성 (품질 중심)

---

## 4. 🧪 트러블슈팅 (Troubleshooting)

### 4.1 순환 의존성(Cyclic Dependency) 해결
*   **문제**: A 에이전트와 B 에이전트가 서로를 참조하여 실행 계획(DAG) 생성 시 무한 루프 발생 가능성.
*   **해결**: Topological Sort 알고리즘에 **DFS 기반 Cycle Detection**을 추가하여, 순환 감지 시 자동으로 우선순위 기반 순차 실행으로 전환(Fallback)하도록 구현했습니다.

### 4.2 복잡한 분기 처리의 안전성 확보
*   **문제**: 사용자 입력에 따라 워크플로우 경로가 동적으로 바뀔 때 상태 관리의 어려움.
*   **해결**: `PlanCraftState`를 `TypedDict`로 명확히 정의하고, `update_state` 헬퍼 함수를 통해 불변성(Immutability)을 유지하며 상태를 안전하게 갱신했습니다.

---

## 5. ✅ 결론 (Conclusion)

본 프로젝트는 AI Bootcamp에서 습득한 모든 기술 요소를 유기적으로 결합하여, 실무에서 즉시 활용 가능한 수준의 **"협업하는 AI 팀"**을 구현해냈습니다.
단순한 자동화를 넘어, **인간의 의도를 이해하고(HITL), 도구를 자유자재로 다루며(A2A), 스스로 계획을 수립하는(Plan-and-Execute)** 진정한 의미의 Agent System을 입증했습니다.

---
*Github: [https://github.com/skyasu2/skax](https://github.com/skyasu2/skax)*
