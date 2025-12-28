# Changelog

모든 주요 변경 사항을 이 파일에 기록합니다.

## [2.0.1] - 2024-12-29

### Added
- **Refiner 재작성 루프 구현** (`graph/workflow.py`)
  - Reviewer가 REVISE 판정 시 `structure → write → review` 루프 재실행
  - 최대 3회까지 자동 개선 후 완료
  - `should_refine_again()` 조건부 엣지 추가
- **Refiner 루프 테스트** (`tests/test_scenarios.py`)
  - 시나리오 D: REVISE/PASS 판정에 따른 라우팅 검증

### Changed
- **LangGraph V0.5+ 호환성 개선**
  - `input` → `input_schema`, `output` → `output_schema` 파라미터명 변경
- **워크플로우 다이어그램 갱신**
  - Refinement Loop 시각화 추가

---

## [2.0.0] - 2024-12-29

### Breaking Changes
- **State Management 전면 리팩토링**: Pydantic BaseModel → TypedDict 전환
  - LangGraph 공식 Best Practice 100% 준수
  - dot-access (`state.field`) → dict-access (`state.get("field")`) 패턴 일괄 적용

### Added
- **TypedDict 헬퍼 함수** (`graph/state.py`)
  - `create_initial_state()`: 초기 상태 생성
  - `update_state()`: 불변성 보장 상태 업데이트 (Partial dict 반환)
  - `safe_get()`: dict/Pydantic 객체 모두에서 안전한 값 추출
  - `validate_state()`: 런타임 상태 검증
- **Input/Output 스키마 분리**
  - `PlanCraftInput`: 외부 API/UI 입력용
  - `PlanCraftOutput`: 외부 API/UI 출력용
  - `PlanCraftState`: 내부 전체 상태 (Input + Output + Internal)
- **Interrupt 필드 추가** (`PlanCraftState`)
  - `confirmed`: 사용자 확인 여부
  - `uploaded_content`: 업로드 콘텐츠
  - `routing_decision`: 라우팅 결정값
- **Time-Travel 테스트** (`tests/test_time_travel.py`)
- **고급 시나리오 테스트** (`tests/test_scenarios.py`)
  - Human Interrupt 플로우
  - Error & Retry 플로우
  - General Query 라우팅

### Changed
- **모든 Agent 반환 패턴 통일**
  - `return update_state(state, **updates)` 패턴 전면 적용
  - 직접 dict 반환 제거
- **노드 함수 리팩토링**
  - `_update_step_history()` 헬퍼로 이력 관리 통일
  - `handle_node_error` 데코레이터로 에러 핸들링 일원화
- **문서 갱신**
  - `README.md`: TypedDict 기반 State Management 섹션 추가
  - `docs/architecture.md`: LangGraph Best Practice 적용 현황 테이블 추가

### Fixed
- `ui/dialogs.py`: `analysis.key_features` dot-access → `safe_get()` 패턴으로 수정

## [1.4.0] - 2024-12-28

### Added
- **MCP (Model Context Protocol) 완전 통합** (`tools/mcp_client.py`)
  - 2개 MCP 서버 동시 지원 (`mcp-server-fetch`, `tavily-mcp`)
  - `MCPToolkit` 클래스로 통합 관리
  - **Auto Fallback**: Node.js/uvx 미설치 시 자동으로 **Tavily Python SDK** 사용
- **웹 검색 출처 표시** (`agents/formatter.py`)
  - 최종 기획서 하단에 "📚 참고 자료" 섹션 자동 추가
- **MCP 설정 환경변수**
  - `TAVILY_API_KEY`: Tavily API 키
  - `MCP_ENABLED`: MCP 사용 여부 (기본: false)

### Changed
- **폴더 구조 변경 (Refactor)**
  - `mcp/` → `tools/`: Python `mcp` 패키지와의 이름 충돌 해결
- **안전성 개선**
  - Streamlit 환경 호환성: `nest_asyncio` 도입으로 이벤트 루프 충돌 방지
  - `search_sync` / `fetch_url_sync`: 동기 환경용 래퍼 함수 고도화
- `WebClient` 생성자에 `use_mcp` 파라미터 추가

### Removed
- **DuckDuckGo 검색 제거**: Tavily MCP 및 Python SDK로 완전 대체
- `duckduckgo-search` 패키지 의존성 제거

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
