# 🧠 PlanCraft Multi-Agent Architecture

> LangGraph StateGraph 기반 Multi-Agent 워크플로우 구성도

---

## 📊 1. 전체 시스템 아키텍처

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#4493f8', 'primaryTextColor': '#fff', 'lineColor': '#58a6ff'}}}%%

graph TB
    subgraph UI["🖥️ Frontend Layer"]
        STREAMLIT[Streamlit UI<br/>사용자 인터페이스]
    end
    
    subgraph API["🔌 API Layer"]
        FASTAPI[FastAPI Server<br/>REST API v1]
    end
    
    subgraph ORCHESTRATOR["🧠 Orchestration Layer"]
        LANGGRAPH[LangGraph StateGraph<br/>워크플로우 엔진]
    end
    
    subgraph AGENTS["🤖 Agent Layer"]
        direction LR
        ANALYZER[🔍 Analyzer]
        STRUCTURER[📐 Structurer]
        WRITER[✍️ Writer]
        REVIEWER[🔎 Reviewer]
        REFINER[✨ Refiner]
        FORMATTER[📄 Formatter]
    end
    
    subgraph SPECIALISTS["🎯 Specialist Layer"]
        direction LR
        MARKET[📈 Market]
        BM[💼 BM]
        RISK[⚠️ Risk]
        TECH[🛠️ Tech]
        CONTENT[📝 Content]
    end
    
    subgraph EXTERNAL["🌐 External Services"]
        direction LR
        AOAI[Azure OpenAI<br/>GPT-4o]
        TAVILY[Tavily<br/>Web Search]
        FAISS[FAISS<br/>Vector Store]
        LANGSMITH[LangSmith<br/>Tracing]
    end
    
    STREAMLIT <-->|HTTP| FASTAPI
    FASTAPI <--> LANGGRAPH
    LANGGRAPH --> AGENTS
    WRITER --> SPECIALISTS
    SPECIALISTS --> WRITER
    AGENTS --> EXTERNAL
    
    style STREAMLIT fill:#ff4b4b,color:#fff
    style FASTAPI fill:#009688,color:#fff
    style LANGGRAPH fill:#8957e5,color:#fff
```

---

## 📊 2. 워크플로우 상세 (Workflow Graph)

```mermaid
%%{init: {'theme': 'base'}}%%

flowchart TD
    START([🚀 START]) --> CONTEXT
    
    subgraph CONTEXT["📚 Context Gathering"]
        RAG[retrieve_context<br/>FAISS RAG]
        WEB[fetch_web_context<br/>Tavily Search]
        RAG --> WEB
    end
    
    CONTEXT --> ANALYZE[🔍 Analyzer<br/>요구사항 분석]
    
    ANALYZE -->|need_more_info| HITL
    ANALYZE -->|is_general| GENERAL[💬 일반 응답]
    ANALYZE -->|ready| STRUCTURE
    
    subgraph HITL["💬 Human-in-the-Loop"]
        OPTION[option_pause_node<br/>interrupt & wait]
    end
    
    HITL -->|user_response| ANALYZE
    GENERAL --> END_NODE
    
    STRUCTURE[📐 Structurer<br/>목차 설계] --> WRITE
    
    subgraph QA_LOOP["🔄 Quality Assurance Loop"]
        WRITE[✍️ Writer<br/>콘텐츠 작성]
        REVIEW[🔎 Reviewer<br/>품질 평가]
        REFINE[✨ Refiner<br/>피드백 개선]
        
        WRITE --> REVIEW
        REVIEW -->|score<9| REFINE
        REFINE --> STRUCTURE
    end
    
    REVIEW -->|score≥9 PASS| FORMAT[📄 Formatter<br/>최종 문서]
    REVIEW -->|FAIL| ANALYZE
    
    FORMAT --> END_NODE([🏁 END])
    
    style START fill:#3fb950,color:#fff
    style END_NODE fill:#f85149,color:#fff
    style HITL fill:#db61a2,color:#fff
    style QA_LOOP fill:#21262d,color:#fff
```

---

## 📊 3. Agent 협업 구조

```mermaid
%%{init: {'theme': 'base'}}%%

graph LR
    subgraph INPUT["📥 Input"]
        USER[👤 User Input]
    end
    
    subgraph CORE_AGENTS["🤖 Core Agents"]
        A1[🔍 Analyzer]
        A2[📐 Structurer]
        A3[✍️ Writer]
        A4[🔎 Reviewer]
        A5[✨ Refiner]
        A6[📄 Formatter]
    end
    
    subgraph SPECIALISTS["🎯 Specialist Squad"]
        S1[📈 Market Agent<br/>TAM/SAM/SOM 분석]
        S2[💼 BM Agent<br/>수익 모델 설계]
        S3[⚠️ Risk Agent<br/>리스크 평가]
        S4[🛠️ Tech Agent<br/>기술 스택 설계]
        S5[📝 Content Agent<br/>마케팅 전략]
    end
    
    subgraph OUTPUT["📤 Output"]
        PLAN[📋 기획서]
    end
    
    USER --> A1
    A1 --> A2
    A2 --> A3
    A3 --> S1 & S2 & S3 & S4 & S5
    S1 & S2 & S3 & S4 & S5 --> A3
    A3 --> A4
    A4 -->|REVISE| A5
    A5 --> A2
    A4 -->|PASS| A6
    A6 --> PLAN
    
    style A1 fill:#d29922,color:#fff
    style A4 fill:#58a6ff,color:#fff
    style PLAN fill:#3fb950,color:#fff
```

---

## 📊 4. Supervisor + Specialist (2-Stage Search)

> **2단계 검색 구조 (Active Search)**:
> 1. Supervisor 단계에서 '넓은 초기 검색' 수행
> 2. Market Agent 내부에서 '정밀 보강 검색(ReAct)' 수행 (최대 2회)

```mermaid
%%{init: {'theme': 'base'}}%%

graph TB
    subgraph STAGE1["Stage 1: Broad Search"]
        SUP[🎖️ Supervisor]
        WEB_CTX[🌐 Initial Web Context<br/>(Executor Result)]
        SUP --> WEB_CTX
    end

    subgraph STAGE2["Stage 2: Active Deep Search"]
        MARKET[📈 Market Agent<br/>(ReAct Agent)]
        
        WEB_CTX --> MARKET
        
        MARKET -->|1. 분석| CHECK{정보 부족?}
        CHECK -->|Yes| SEARCH[🔍 Tavily Active Search]
        SEARCH -->|Result| MARKET
        
        CHECK -->|No / Limit| OUTPUT[📋 Market Analysis<br/>JSON]
        
        style SEARCH fill:#ff9f1c,color:#fff
    end
    
    SUPERVISOR --> MARKET
    
    MARKET -->|Result| MERGE[📦 Result Merger]
    
    style SUP fill:#8957e5,color:#fff
    style MARKET fill:#d29922,color:#fff
```

---

## 📊 5. Human-in-the-Loop (HITL) 상세 흐름

> **Side-Effect Free 원칙**: `interrupt` 이전에 DB 저장을 절대 하지 않음!

```mermaid
%%{init: {'theme': 'base'}}%%

sequenceDiagram
    participant U as 👤 User
    participant A as 🔍 Analyzer
    participant H as 💬 HITL Node
    participant W as ✍️ Writer
    
    U->>A: "AI 앱 만들어줘"
    A->>A: 분석 (모호함 감지)
    
    rect rgb(255, 240, 240)
        Note over A, H: 🛑 SIDE-EFFECT BARRIER 🛑<br/>(No DB Save, No API Call)
        A->>H: interrupt(payload)
    end
    
    H-->>U: "어떤 방향으로 진행할까요?" (UI)
    Note over H: ⏸️ 워크플로우 일시정지 (Wait)
    
    U->>H: resume(command={"resume": "옵션A"})
    
    rect rgb(240, 255, 240)
        Note over H, A: ✅ RESUME & RE-EXECUTE
        H->>A: Payload 전달 (State Update)
        A->>A: 재분석 (명확해짐)
        A->>W: 기획서 작성 진행
    end
    
    W-->>U: 📋 완성된 기획서
```

---

## 📊 6. 품질 루프 (QA Loop) 상태 전이

```mermaid
%%{init: {'theme': 'base'}}%%

stateDiagram-v2
    [*] --> Writing: 구조 설계 완료
    
    Writing --> Reviewing: 초안 작성 완료
    
    Reviewing --> Formatting: score≥9 & PASS
    Reviewing --> Refining: 5≤score<9
    Reviewing --> Analyzing: score<5 | FAIL
    
    Refining --> Writing: 개선 전략 수립
    
    Formatting --> [*]: 최종 문서 생성
    
    Analyzing --> Writing: 재분석 완료
    
    note right of Reviewing
        최대 3회 반복
        (무한 루프 방지)
    end note
```

---

## 📊 7. PlanCraftState 데이터 흐름

```mermaid
%%{init: {'theme': 'base'}}%%

flowchart LR
    subgraph Input
        UI[user_input]
        FILE[file_content]
    end
    
    subgraph Context
        RAG[rag_context]
        WEB[web_context<br/>web_sources]
    end
    
    subgraph Analysis
        ANA[analysis<br/>AnalysisResult]
        STR[structure<br/>StructureResult]
    end
    
    subgraph Draft
        DFT[draft<br/>DraftResult]
        REV[review<br/>JudgeResult]
    end
    
    subgraph Output
        FINAL[final_output<br/>Markdown]
    end
    
    UI & FILE --> Context
    Context --> Analysis
    Analysis --> Draft
    Draft --> Output
    
    style FINAL fill:#3fb950,color:#fff
```

---

## 📊 9. MCP (Model Context Protocol) Architecture

> **Client Mode Implementation**:
> PlanCraft App이 `mcp-client` 역할을 수행하며, 표준 입출력(stdio)을 통해
> 외부 MCP 서버(Tavily, Fetch 등)와 통신합니다.

```mermaid
%%{init: {'theme': 'base'}}%%

graph LR
    subgraph APP["🖥️ PlanCraft Application (Client)"]
        CLIENT[MCP Client Module<br/>(mcp_client.py)]
    end
    
    subgraph MCP_SERVERS["🔌 MCP Servers (Providers)"]
        direction TB
        
        subgraph TAVILY["🔍 tavily-mcp"]
            NPX[npx @tavily-ai/mcp-server]
        end
        
        subgraph FETCH["🌐 fetch-mcp"]
            UVX[uvx mcp-server-fetch]
        end
    end
    
    CLIENT <==>|stdio / JSON-RPC| NPX
    CLIENT <==>|stdio / JSON-RPC| UVX
    
    NPX -->|API Call| WEB[Tavily API]
    UVX -->|HTTP GET| SITE[Target Website]
    
    style CLIENT fill:#0969da,color:#fff
    style TAVILY fill:#d29922,color:#fff
    style FETCH fill:#1f883d,color:#fff
```

---

*Generated by PlanCraft Multi-Agent System*
