# Changelog

모든 주요 변경 사항을 이 파일에 기록합니다.

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
