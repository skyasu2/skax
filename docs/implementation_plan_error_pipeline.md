# Implementation Plan - Robust Error Handling Pipeline

This plan focuses on standardizing error handling across the PlanCraft agent using decorators and consistent state management, as requested.

## User Review Required

> [!NOTE]
> I will replace individual `try-except` blocks in node functions with a `@handle_node_error` decorator. This improves code cleanliness and ensures every error is caught and recorded in the state uniformly.

## Proposed Changes

### 1. State Schema (`graph/state.py`)
- Add `error_message` property (or field) to `PlanCraftOutput` and `PlanCraftState` to align with user request.
- Ensure `retry_count` is passed correctly.

### 2. Utility (`utils/error_handler.py`)
- **`@handle_node_error`**:
    - Wraps node functions.
    - On Exception:
        - Logs the error.
        - Updates `state.error` (and `error_message`).
        - Sets `state.step_status = "FAILED"`.
        - Returns the updated state (preventing graph crash).

### 3. Workflow (`graph/workflow.py`, `agents/`)
- Apply `@handle_node_error` to:
    - `run_analyzer_node`, `run_writer_node`, etc.
    - `run_context_subgraph` (if applicable).
- Remove manual try-except blocks where the decorator covers it.

### 4. UI (`ui/components.py`)
- Update `render_error_state` to use the standardized fields.
- Add "Smart Recovery" options if possible (e.g., if error is "API Key Missing", show input form).

## Verification Plan
1. **Automated Test**: Add a test case that injects a mocked failure into a node and asserts that the state is updated with `error_message` and `FAILED` status, instead of crashing.
2. **Manual Test**: Manually trigger an error (e.g., disconnect network or bad API key) and verify the fallback UI.
