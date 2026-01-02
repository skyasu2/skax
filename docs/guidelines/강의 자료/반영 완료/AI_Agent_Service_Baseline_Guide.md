# End-to-End AI Agent Service 개발 기준 가이드
(Streamlit · LangGraph · RAG · Multi-Agent)

## 1. 문서 목적
본 문서는 AI Bootcamp에서 학습한 서비스 개발 및 패키징 강의 내용을 기반으로,
최종 과제인 End-to-End AI Agent 서비스 개발을 수행하기 위한 기준선 가이드이다.

## 2. 최종 과제 핵심 정의
Prompt → Agent 설계 → 실행 워크플로우 → RAG → UI/패키징까지 연결된 완결형 AI Agent 서비스 구현

## 3. 전체 아키텍처 기준
UI(Streamlit) → Agent Orchestration(LangGraph) → Multi-Agent Nodes → RAG/Tools → State/Memory

## 4. Streamlit 개발 기준
- UI 전용 레이어
- 입력, 진행 상태, 스트리밍, 히스토리 관리 담당

## 5. Multi-Agent 설계
- 단일 Agent 불가
- LangGraph 기반 Node / Edge / Conditional Edge 필수

## 6. 상태 관리
- UI 상태: Streamlit Session State
- Agent 상태: LangGraph State

## 7. RAG 필수 기준
- Embedding + Vector Store + Similarity Search
- 검색 결과 Prompt 주입

## 8. 스트리밍
- LangGraph stream mode
- 실시간 Node 실행 출력

## 9. 서비스 패키징
- Streamlit UI
- (권장) FastAPI Backend 분리

## 10. 평가 기준
- 문제 정의 명확성
- Agent 역할 분리
- LangGraph 사용 타당성
- RAG 실효성
- UX 완성도
