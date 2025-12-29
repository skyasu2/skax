# PlanCraft Agent - 문서 목록

## 📚 핵심 문서

| 문서 | 설명 | 대상 |
|------|------|------|
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | **프로젝트 전체 구조** (Quick Reference 포함) | 모든 개발자 |
| [SYSTEM_DIAGRAM.md](SYSTEM_DIAGRAM.md) | 시스템 전체 구조도 (ASCII 다이어그램) | 아키텍처 이해 |
| [architecture.md](architecture.md) | 시스템 아키텍처 상세 | 설계 검토 |
| [agent-design.md](agent-design.md) | 6 Agent 설계 문서 | Agent 개발 |

## 🔧 개발 가이드

| 문서 | 설명 |
|------|------|
| [deployment-guide.md](deployment-guide.md) | 배포 가이드 (로컬/Docker/클라우드) |
| [human-interrupt-guide.md](human-interrupt-guide.md) | LangGraph Human Interrupt Best Practice |
| [api-spec.md](api-spec.md) | API 명세 |
| [web-search-design.md](web-search-design.md) | 웹 검색 (Tavily) 설계 |

## 📊 다이어그램

| 파일 | 형식 | 용도 |
|------|------|------|
| [architecture.mermaid](architecture.mermaid) | Mermaid | GitHub 렌더링용 |

---

## 📝 문서 관리 규칙

1. **핵심 문서 4개**는 코드 변경 시 함께 업데이트
2. **Quick Reference**는 `PROJECT_STRUCTURE.md` 상단에 통합
3. **중복 문서 금지** - 하나의 주제는 하나의 문서에서 관리
