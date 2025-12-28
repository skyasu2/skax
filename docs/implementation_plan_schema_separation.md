# Implementation Plan - LangGraph Input/Output Schema Separation

This plan refactors the `PlanCraftState` to clearly distinguish between public inputs/outputs and internal working state, following LangGraph best practices.

## User Review Required

> [!IMPORTANT]
> This is a structural refactor. While it improves architecture, it changes how `StateGraph` is initialized. `PlanCraftState` will effectively become the `OverallState`.

## Proposed Changes

### 1. Schema Definition (`graph/state.py`)
- **Current**: Single `PlanCraftState(BaseModel)` for everything.
- **New Structure**:
    - `PlanCraftInput(BaseModel)`: `user_input`, `file_content`, `refine_count`, `thread_id`.
    - `PlanCraftOutput(BaseModel)`: `final_output`, `step_history`, `summary` (optional).
    - `PlanCraftState(PlanCraftInput, PlanCraftOutput)`: Adds internal fields like `analysis`, `structure`, `draft`, `error`, etc.
    *Using Pydantic for all ensures validation, similar to TypedDict but stronger.*

### 2. Workflow Update (`graph/workflow.py`)
- `workflow = StateGraph(PlanCraftState, input=PlanCraftInput, output=PlanCraftOutput)`
- This explicitly declares the contract.

### 3. Application Update (`app.py`, `graph/workflow.py`)
- `run_plancraft` currently creates `initial_state` manually.
- With the new pattern, `invoke` handles input validation. We can simplify `run_plancraft` to pass a dict matching `PlanCraftInput`.

## Verification Plan
1. **Schema Introspection**: `print(app.get_graph().input_schema.schema())` to verify only input fields are required.
2. **Regression Test**: Run `pytest` to ensure the graph still flows correctly.
3. **UI Verification**: Ensure Streamlit app still works (as it reads from the state, which will still be the full `PlanCraftState` internally).
