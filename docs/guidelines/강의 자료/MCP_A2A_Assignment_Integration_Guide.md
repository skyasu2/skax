# MCP & A2A 강의 내용 분석 기반  
## 최종 과제 반영 가이드 (도입 포인트 정리)

본 문서는 **MCP(Model Context Protocol)** 및 **A2A(Agent-to-Agent)** 강의 자료를 분석하여,  
현재까지 구현된 AI 에이전트 과제에 **실제로 도입·반영해야 할 핵심 요소만** 정리한 가이드이다.

---

## 1. MCP 분석 → 과제 반영 포인트

### 1.1 MCP의 핵심 정의
- MCP는 LLM에 맥락(Context)을 전달하는 표준 프로토콜
- Context 구성 요소:
  - System Prompt
  - 대화 히스토리
  - Tool 호출 결과
  - RAG 결과
  - Agent 이전 단계 결과

### 1.2 과제 반영 핵심
- Context 출처를 계층적으로 명시
- MCP Host / Client / Server 개념을 현재 구조에 매핑

---

## 2. A2A 분석 → 과제 반영 포인트

### 2.1 A2A 핵심 개념
- 내부 구현을 알 필요 없는 Agent 간 통신 표준
- 독립성, 상호운용성, 확장성 확보

### 2.2 과제 반영 핵심
- Agent 간 직접 의존성 제거
- Capability 기반 Agent 설명(Agent Card 개념)

---

## 3. MCP + A2A 결합 관점
- MCP: Context 전달 표준
- A2A: Agent 협업 표준

---

## 4. 과제에 실제로 추가할 것 요약
1. MCP Context 계층 설명 문서화
2. MCP 구성요소 매핑 표
3. Agent Capability 명세
4. A2A 설계 문장 추가

---

## 5. 결론
지금 과제는 이미 구조적으로 MCP/A2A를 충족하며,  
남은 것은 이를 명확히 설명하는 문서 보완이다.

---

### 참고 자료
- MCP 및 A2A 강의 자료 (AI 혁신팀, 김지환)
