# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language Preference / 언어 설정

**한국어로 우선 답변할 것. 기술적 표현은 영어 사용 가능.**

Respond in Korean first. Technical terms may be in English.

## Project Overview

PlanCraft Agent is an AI-powered business plan generation system using a Multi-Agent architecture. Users input an idea, and 10 AI agents collaborate to generate professional-grade planning documents.

**Core Technologies**: LangGraph v0.5+, LangChain v0.2+, Azure OpenAI (GPT-4o), FastAPI, Streamlit, FAISS

## Common Commands

```bash
# Run the Streamlit app (main entry point)
streamlit run app.py

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_agents.py -v

# Run tests with coverage
python -m pytest tests/ --cov=. --cov-report=html

# Run specific test markers
python -m pytest tests/ -m "not slow"        # Skip slow tests
python -m pytest tests/ -m "integration"     # Integration tests only

# Start FastAPI server directly (usually auto-started by Streamlit)
uvicorn api.main:app --reload --port 8000
```

## Architecture

### Multi-Agent Workflow (LangGraph StateGraph)

```
START → context_gathering → analyze → structure → write (ReAct) → review → [discussion] → refine → format → END
                              ↓                       ↓                        ↓                          ↑
                        option_pause (HITL)   [Thought→Action→Obs]        [score < 9]─────────────────────┘
                              ↓                       ↓                        ↓
                            END              도구 자율 호출 (최대3회)    [score < 5] → analyze (restart)
```

**Multi-Agent Collaboration**:
- **Writer ReAct 패턴**: Writer가 작성 중 데이터 부족 판단 시 자율적으로 도구 호출 (Balanced/Quality 프리셋)
  - `request_specialist_analysis`: Specialist 에이전트에게 추가 분석 요청
  - `search_rag_documents`: 내부 RAG 문서 검색
  - `search_web`: 웹 검색
- **Co-authoring**: Reviewer ↔ Writer가 LLM 기반 합의까지 대화 (최대 5라운드)

**10 Agents**:
- **Analyzer**: Parses user requirements, detects ambiguity (triggers HITL)
- **Structurer**: Designs document outline (9-13 sections based on preset)
- **Supervisor**: Orchestrates Specialist Squad (Plan-and-Execute pattern)
- **Specialists** (Market/BM/Risk/Tech): Parallel domain-specific analysis
- **Writer**: Generates section content with ReAct pattern (autonomous tool calling)
- **Reviewer**: Evaluates quality (PASS ≥9 / REVISE 5-8 / FAIL <5)
- **Refiner**: Creates improvement strategies based on feedback
- **Formatter**: Produces final output with chat summary

### Key State Management (`graph/state.py`)

- **PlanCraftInput**: External API input schema
- **PlanCraftOutput**: External API output schema
- **PlanCraftState**: Internal TypedDict containing all workflow state
- Use `update_state(state, **kwargs)` for immutable state updates
- Use `ensure_dict(obj)` to normalize Pydantic models to dicts

### Quality Presets (`utils/settings.py`)

| Preset | Model | Max Refine | Writer ReAct | Features |
|--------|-------|------------|--------------|----------|
| fast | gpt-4o-mini | 1 | ❌ | Basic MMR search |
| balanced | gpt-4o | 2 | ✅ (3 calls) | Multi-Query + Reranking |
| quality | gpt-4o | 3 | ✅ (3 calls) | Full RAG + Deep Analysis |

Access via: `from utils.settings import get_preset; preset = get_preset("quality")`

### Human-in-the-Loop (HITL)

LangGraph `interrupt()` is used for user interaction. **Critical rules**:
1. **No side-effects before interrupt()**: Resume re-executes from the node start
2. Side-effects (DB writes, API calls) must come AFTER interrupt()
3. Interrupt payloads defined in `graph/interrupt_utils.py`

### Directory Structure Notes

- `agents/`: Agent implementations (each has `.run()` method)
- `graph/nodes/`: Extracted node functions (decorators: `@trace_node`, `@handle_node_error`)
- `graph/subgraphs.py`: Sub-graph patterns (Context, Generation, QA)
- `prompts/`: LLM prompt templates (Korean language)
- `rag/`: FAISS vectorstore + retriever with advanced features
- `tools/`: Agent tools (Writer ReAct tools: `writer_tools.py`)
- `ui/`: Streamlit components (tabs/, modules/, dialogs/)
- `utils/schemas.py`: Pydantic schemas for agent outputs (AnalysisResult, JudgeResult, etc.)

## Code Patterns

### Agent Node Template
```python
@trace_node("node_name", tags=["category"])
@handle_node_error
def run_agent_node(state: PlanCraftState) -> PlanCraftState:
    from graph.state import update_state, ensure_dict

    # Access preset settings
    preset = get_preset(state.get("generation_preset", "balanced"))

    # Call agent
    result = agent.run(state)
    result_dict = ensure_dict(result)

    # Return updated state (immutable)
    return update_state(state, agent_output=result_dict, current_step="agent_name")
```

### Routing Functions
Routing returns `Literal` types matching `add_conditional_edges` keys:
```python
def should_route(state: PlanCraftState) -> Literal["next_a", "next_b"]:
    if condition:
        return RouteKey.OPTION_A  # Use RouteKey enum
    return RouteKey.OPTION_B
```

### LLM Usage
```python
from utils.llm import get_llm, get_llm_with_retry

# Production (with retry)
llm = get_llm_with_retry(temperature=0.7)

# Structured output
from utils.schemas import AnalysisResult
llm_structured = llm.with_structured_output(AnalysisResult)
result = llm_structured.invoke(prompt)
```

## Environment Setup

Required in `.env`:
```bash
AOAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AOAI_API_KEY=your_api_key
```

Optional:
```bash
TAVILY_API_KEY=...        # Web search
LANGCHAIN_TRACING_V2=true # LangSmith tracing
LANGCHAIN_API_KEY=...
```

## Testing Notes

- Tests use `pytest-asyncio` for async tests
- Mock LLM calls to avoid API costs: use `unittest.mock.patch`
- Test markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.e2e`
- Current status: 308+ tests (some require API keys)

## Important Thresholds (`utils/settings.py`)

```python
QualityThresholds.SCORE_PASS = 9      # Review passes
QualityThresholds.SCORE_FAIL = 5      # Triggers restart
QualityThresholds.MAX_RESTART_COUNT = 2
QualityThresholds.MAX_REFINE_LOOPS = 3
```

## Debugging

- LangSmith: Set `LANGCHAIN_TRACING_V2=true` for trace visualization
- File logs: `utils/file_logger.py` outputs to `logs/` directory
- JSON logging: `utils/logging_config.py` with structured format
