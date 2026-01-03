# Prompt Engineering 강의 자료 분석 요약

## 1. 강의 목적 요약
본 강의는 **LLM을 잘 쓰는 법이 아니라, 원하는 결과를 안정적으로 얻는 방법**을 다룬다.  
즉, Prompt Engineering을 *요령*이 아닌 **설계 기술(Engineering)** 로 이해시키는 것이 핵심 목적이다.

---

## 2. Prompt Engineering의 정의

### 2.1 기본 정의
Prompt Engineering이란:
> LLM이 **의도한 출력**을 생성하도록  
입력 구조, 지시문, 제약 조건, 예시를 체계적으로 설계하는 기술

### 2.2 핵심 전제
- LLM은 추론 엔진이 아니라 **확률 기반 생성기**
- 명확한 입력 없이는 **일관된 출력 불가**

---

## 3. 왜 Prompt Engineering이 중요한가

### 3.1 문제 상황
- 같은 질문 → 다른 답변
- 긴 답변, 핵심 누락
- 포맷 불일치
- Hallucination 발생

### 3.2 해결 방향
- Prompt 구조화
- 역할(Role) 명시
- 출력 포맷 고정

📌 **강의 핵심 메시지**  
> 모델 성능보다 Prompt 설계가 결과 품질을 더 크게 좌우한다.

---

## 4. Prompt 기본 구성 요소

### 4.1 Role
- 모델의 역할을 명확히 지정
- 예: “당신은 시니어 백엔드 아키텍트입니다”

### 4.2 Task
- 수행해야 할 작업을 구체적으로 명시
- 추상적 요청 ❌ / 단계적 요청 ⭕

### 4.3 Context
- 배경 정보 제공
- 도메인, 제약, 사용 목적

### 4.4 Output Format
- JSON / Markdown / Table 등
- 포맷 지정 시 응답 품질 급상승

---

## 5. Prompt 패턴 정리

### 5.1 Zero-shot Prompt
- 예시 없이 바로 요청
- 단순 작업에 적합

### 5.2 Few-shot Prompt
- 입력/출력 예시 제공
- 포맷·스타일 고정에 효과적

### 5.3 Chain-of-Thought (CoT)
- 단계별 사고 유도
- 복잡한 추론 문제에 유리

📌 단, 과도한 CoT는 비용·지연 증가

---

## 6. Structured Output Prompt

### 6.1 필요성
- 후처리 비용 감소
- 파싱 안정성 확보
- Agent/Workflow 연계 필수

### 6.2 예시
```json
{
  "summary": "",
  "issues": [],
  "recommendations": []
}
```

📌 LangChain / LangGraph와 자연스럽게 연결됨

---

## 7. Prompt와 Agent의 관계

### 7.1 Prompt는 Agent의 두뇌
- Agent 행동의 기준
- Tool 사용 여부 판단 근거

### 7.2 Prompt Drift 문제
- 반복 호출 시 지시 무력화
- 해결책:
  - System Prompt 고정
  - 상태 최소화
  - 출력 검증

---

## 8. 실무에서의 Prompt Engineering 전략

### 8.1 프롬프트는 코드처럼 관리
- 버전 관리
- 주석
- 변경 이력 기록

### 8.2 테스트 필수
- 동일 입력 반복 테스트
- Edge Case 확인

---

## 9. 과제 및 프로젝트 적용 포인트

### 필수 적용
- Role / Task / Output 분리
- 출력 포맷 명시
- 프롬프트 파일 분리 관리

### 가점 요소
- Few-shot 예시 사용
- Structured Output 적용
- Prompt 선택 이유 문서화

---

## 10. 강의 핵심 메시지 요약

1. Prompt는 감이 아니라 설계 대상
2. 출력 포맷 지정은 필수
3. Agent 구조에서 Prompt는 핵심 자산
4. 테스트와 관리 없이는 품질 유지 불가
5. “왜 이 프롬프트인가”를 설명할 수 있어야 한다

---

### 한 줄 결론
> **Prompt Engineering은 요령이 아니라  
LLM 기반 시스템의 품질을 결정하는 핵심 설계 요소다.**
