# RAG 데이터 기반 AI 활용 – 강의 내용 분석 요약

## 1. 강의 목적 요약
본 강의는 **RAG(Retrieval Augmented Generation)** 기반 AI 서비스를 설계·구현하기 위해  
개념 이해 → 기본 파이프라인 → 한계 → 고도화 전략까지 **실무 중심**으로 설명하는 것을 목표로 한다.

---

## 2. RAG가 필요한 이유 (Hallucination 문제)

### 2.1 Hallucination 정의
- LLM이 **사실이 아닌 정보를 그럴듯하게 생성**하는 문제
- 최신 정보, 특정 도메인 정보 질문 시 빈번히 발생

### 2.2 RAG의 핵심 가치
- LLM이 **외부 신뢰 가능한 데이터**를 참고하도록 강제
- “기억해서 답변” ❌ → “찾아서 답변” ⭕

---

## 3. RAG vs Fine-tuning

| 구분 | RAG | Fine-tuning |
|----|----|----|
| 개념 | 외부 문서 검색 후 응답 | 모델 자체 재학습 |
| 비용 | 낮음 | 높음 (GPU, 시간) |
| 최신성 | 문서 업데이트만으로 반영 | 재학습 필요 |
| 위험 | 검색 품질 의존 | 과적합 가능 |

📌 **강의 결론**  
> 대부분의 서비스형 AI는 Fine-tuning보다 RAG가 현실적이다.

---

## 4. Naïve RAG 기본 Workflow

### 4.1 전체 흐름
1. Knowledge Base 구축  
2. 문서 전처리 (Extract / Split)  
3. Embedding  
4. Vector DB Indexing  
5. Retrieval  
6. Generation  

---

## 5. Knowledge Base 구축 핵심

### 5.1 문서 전처리 단계
- **Extract Text**
  - PDF (Searchable / Image-based)
  - OCR 필요 여부 판단
- **Split Text**
  - Fixed chunk / Overlap
  - Semantic chunking
- **Embedding**
  - 문서를 벡터로 변환
- **Indexing**
  - Vector DB 저장

📌 Chunk 품질이 RAG 품질의 절반 이상을 결정

---

## 6. Vector DB & Indexing 이해

### 6.1 Indexing 방식
- Flat Index: 정확하지만 느림
- IVF / PQ: 속도 개선, 정확도 일부 손실
- HNSW: 대규모 서비스에서 가장 많이 사용

### 6.2 Vector DB 비교
- Chroma: 간단, 실습용
- Qdrant: REST API, 필터링 강점
- Milvus: 대규모, K8s 친화

---

## 7. Retriever 전략

### 7.1 기본 검색 방식
- Similarity (Top-k)
- Similarity + Threshold
- MMR (중복 최소화)

### 7.2 고급 Retriever
- Multi-query Retriever
- Long Context Reorder

📌 Retrieval 품질이 곧 응답 품질

---

## 8. Naïve RAG의 한계

- 검색 문서 부정확
- 문서 길이 제한
- Re-ranking 부재
- Hallucination 완전 제거 불가

---

## 9. Advanced / Agentic RAG

### 9.1 Advanced RAG
- Pre-Retrieval: Query 변형
- Post-Retrieval: Re-ranking, 요약

### 9.2 Agentic RAG
- LLM이 **스스로 검색 필요성 판단**
- 웹 검색, API 호출 포함

### 9.3 Self-RAG / Corrective RAG
- 답변 자체 검증
- 부족 시 재검색, 재생성

---

## 10. Adaptive RAG
- 질문 유형 분석 후 RAG Flow 분기
- Vector DB → Web → API 동적 라우팅

---

## 11. 실무 사례 – 세무 AI

- 복잡한 도메인 지식
- 법/규정 최신성 중요
- Agentic + RAG 구조 필수

---

## 12. 강의 핵심 메시지 정리

1. RAG는 **검색 품질 싸움**
2. Chunking & Retrieval 설계가 핵심
3. Naïve RAG는 출발점일 뿐
4. 서비스형 AI는 Agentic RAG로 진화
5. 사용자 가치 중심 설계가 최종 목표

---

## 13. 과제 및 프로젝트 적용 시 포인트

- Naïve RAG 구현만 해도 충분히 통과권
- Advanced / Agentic은 **설계 설명만으로도 가점**
- “왜 이 구조를 선택했는가” 설명이 중요

---

### 한 줄 결론
> **RAG는 기술이 아니라 설계 문제이며,  
Agent와 결합될 때 비로소 서비스가 된다.**
