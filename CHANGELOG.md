# Changelog

모든 주요 변경 사항을 이 파일에 기록합니다.

## [1.3.0] - 2024-12-27

### Added
- **Sub-graph 패턴 도입** (`graph/subgraphs.py`)
  - Context Sub-graph: RAG + 웹 검색 그룹화
  - Generation Sub-graph: 분석 → 구조 → 작성 그룹화
  - QA Sub-graph: 검토 → 개선 → 포맷 그룹화
- **Sub-graph 워크플로우** (`create_subgraph_workflow()`)
  - LangGraph 베스트 프랙티스 적용
  - 각 Sub-graph 독립 테스트 가능
- **Sub-graph 테스트** (`tests/test_agents.py`)
  - 각 Sub-graph 생성 검증
  - 워크플로우 통합 검증

### Changed
- `compile_workflow(use_subgraphs=True)` 옵션 추가

## [1.2.0] - 2024-12-27

### Added
- **pytest 단위 테스트** (`tests/test_agents.py`)
  - Pydantic 스키마 검증 테스트
  - State 불변성 테스트
  - Cross-field validation 테스트
- **LangSmith 트레이싱 강화**
  - `@traceable` 데코레이터를 Agent에 적용
  - `Config.setup_langsmith()` 자동 활성화 함수
- **Pydantic Validators 추가**
  - `AnalysisResult`: `need_more_info=True`일 때 `options` 자동 생성
  - `StructureResult`: 빈 `sections` 방지 (기본값 생성)
  - `JudgeResult`: `verdict` 값 자동 보정 (PASS/REVISE/FAIL)
- **State Cross-field Validation**
  - `analysis` 객체와 상위 필드 자동 동기화
  - `error` 발생 시 `current_step`에 `_error` suffix 추가

### Changed
- **Dev Tools 모달화**: 사이드바에서 헤더 버튼 클릭 모달로 변경
- **Few-shot 프롬프트 보강**: 복잡한 케이스(비대면 진료 앱) 예시 추가

### Fixed
- 채팅 입력창 포커스 테두리가 박스와 맞지 않는 CSS 버그 수정

## [1.1.0] - 2024-12-26

### Added
- **Pydantic State Management**: `TypedDict`에서 `Pydantic BaseModel`로 전면 전환
- **Interactive Dev Tools**: Streamlit 사이드바 내 Agent 단위 테스트 도구
- **Human-in-the-loop**: 불명확한 요청 시 사용자에게 옵션 제시

### Changed
- 모든 Agent가 `state.model_copy(update=...)` 패턴으로 불변성 유지
- `with_structured_output()` 패턴 전면 적용

## [1.0.0] - 2024-12-25

### Added
- 초기 릴리스
- 6개 전문 Agent (Analyzer, Structurer, Writer, Reviewer, Refiner, Formatter)
- LangGraph 기반 워크플로우
- RAG Integration (FAISS + text-embedding-3-large)
- 조건부 웹 검색 (DuckDuckGo)
- Streamlit UI
