# 🤖 멀티 에이전트(Multi-Agent) 아키텍처 비교 분석 보고서

본 문서는 **PlanCraft Agent**의 멀티 에이전트 설계가 업계 표준(Best Practices) 및 학술적 에이전트 패턴(Reflexion, Plan-and-Solve 등)과 어떻게 부합하는지 비교 분석한 자료입니다.

---

## 1. 비교 분석 프레임워크 (Comparison Framework)
현대적인 AI Agent 시스템을 평가하는 4가지 핵심 패턴을 기준으로 분석합니다.

1.  **Planning (계획 수립)**: 작업을 즉시 수행하지 않고 단계를 설계하는가?
2.  **Reflection (성찰 및 비평)**: 결과물을 스스로 검토하고 개선(Self-Correction)하는가?
3.  **Collaboration (협업 및 역할 분담)**: 명확한 역할(Persona)이 분리되어 있는가?
4.  **HIL (Human-in-the-Loop)**: 인간의 개입을 구조적으로 허용하는가?

---

## 2. 상세 비교 분석

### ① Planning Pattern (계획 수립)
| 업계 표준 (Standard) | PlanCraft 구현 (Implementation) | 평가 |
|----------------------|---------------------------------|------|
| **Chain of Thought / Plan-and-Solve**<br>복잡한 작업 전, 논리적 단계를 먼저 수립해야 함. | **Executor 분리 설계**<br>- `Analyzer(분석)` → `Structurer(목차 설계)` → `Writer(작성)`<br>- 즉시 작성을 시작하지 않고 구조를 먼저 잡는 **2-Step Planning** 적용 | **Best Practice 일치** ✅<br>(단순 CoT보다 강력한 명시적 단계 분리) |

### ② Reflection Pattern (성찰 및 비평)
| 업계 표준 (Standard) | PlanCraft 구현 (Implementation) | 평가 |
|----------------------|---------------------------------|------|
| **Reflexion (Shinn et al., 2023)**<br>생성(Generator) 후 검증(Verifier) 과정을 통해 품질을 높임. | **Reviewer-Refiner Loop**<br>- `Writer`가 작성한 초안을 `Reviewer`가 10점 만점으로 평가<br>- 기준 점수 미달 시 `Refiner`가 수정을 수행하고 다시 평가받는 **순환 루프(Cycle)** 구현 | **Best Practice 일치** ✅<br>(가장 강력한 품질 보증 패턴 적용) |

### ③ Collaboration Pattern (역할 분담)
| 업계 표준 (Standard) | PlanCraft 구현 (Implementation) | 평가 |
|----------------------|---------------------------------|------|
| **Role-Based Agents (AutoGen/CrewAI)**<br>각 에이전트가 고유한 페르소나와 도구를 가짐. | **5 Specialist Agents**<br>- `Analyzer`: PM 역할 (요구사항 분석)<br>- `Structurer`: 아키텍트 역할 (구조 설계)<br>- `Writer`: 전문 작가 (내용 작성)<br>- `Reviewer`: QA/Auditor (비평)<br>- `Refiner`: 에디터 (수정) | **Best Practice 일치** ✅<br>(역할 혼재 없이 단일 책임 원칙 준수) |

### ④ Human-in-the-Loop (인간 개입)
| 업계 표준 (Standard) | PlanCraft 구현 (Implementation) | 평가 |
|----------------------|---------------------------------|------|
| **Interactive Process**<br>AI가 불확실할 때 인간에게 결정을 위임해야 함. | **State Interrupt & Resume**<br>- 불충분 정보 감지 시 `option_pause_node` 진입<br>- 사용자 응답을 받을 때까지 대기(Wait) 후, 문맥을 유지하며 재개(Resume) | **Best Practice 일치** ✅<br>(LangGraph의 핵심 기능을 정석대로 구현) |

---

## 3. LangGraph 아키텍처 관점 분석

### 3.1 Orchestration vs Choreography
- **PlanCraft는 Orchestration(중앙 제어) 방식에 가깝습니다.**
- **특징**: `StateGraph`가 **지휘자(Conductor)**가 되어 에이전트 간의 이동 경로(Edge)를 명확히 제어합니다.
- **장점**: 업무 프로세스가 예측 가능하며(Deterministic), 무한 루프나 환각(Hallucination)에 빠질 위험이 적습니다. 이는 **비즈니스 애플리케이션(기획서 작성)**에 가장 적합한 모델입니다.

### 3.2 State Management (Blackboard Pattern)
- `PlanCraftState`라는 공유 메모리(Shared State)를 사용합니다.
- 모든 에이전트가 하나의 칠판(State)을 보고 작업물을 갱신(Update)합니다. 이는 데이터 일관성을 유지하는 가장 효율적인 방식입니다.

---

## 4. 종합 결론

> **"교과서적인 Multi-Agent Pipeline 구축 사례"**

PlanCraft Agent는 단순히 여러 프롬프트를 연결한 것이 아닙니다. 
**[분석 → 계획 → 실행 → 평가 → 개선]**으로 이어지는 **Cognitive Architecture(인지 아키텍처)**의 정석을 따르고 있습니다.

특히 **Reviewer-Refiner의 피드백 루프**와 **명시적인 Graph 흐름 제어**는 실무 서비스에서 요구하는 **"안정성 높고 품질이 보장되는 결과물"**을 만드는 데 최적화된 설계입니다.
