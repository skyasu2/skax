# Implementation Plan - Advanced Human Interrupts

This plan implements a generalized interrupt mechanism using `InterruptPayload` and LangGraph's native `interrupt` feature, enabling schema-driven UI automation.

## User Review Required

> [!IMPORTANT]
> This change shifts the interrupt handling from manual State flags (`need_more_info`) to LangGraph's native `interrupt` mechanism. This requires `app.py` to inspect the graph snapshot for interrupts.

## Proposed Changes

### 1. Schema Definition (`utils/schemas.py`)
- **`InterruptPayload(BaseModel)`**:
    - `type`: "option" | "form" | "confirm"
    - `question`: User-facing message.
    - `options`: List of choices (Optional).
    - `input_schema_name`: Pydantic model name for forms (Optional).
    - `data`: Arbitrary dict for extra context.

### 2. Node Implementation (`graph/interrupt_utils.py`)
- **`option_pause_node`**:
    - Construct `InterruptPayload`.
    - Call `interrupt(payload)`.
    - **Crucially**, handling the *return value* of interrupt (which is the user input provided via `Command`).

### 3. Application Logic (`app.py`)
- Instead of checking `state.need_more_info`, check `graph.get_state(config).tasks[0].interrupts`.
- If an interrupt exists:
    - Extract `InterruptPayload`.
    - Call `render_human_interaction(payload)`.
- On Form Submit:
    - Use `Command(resume=user_data)` to resume execution.

## Verification Plan
1. **Interactive Test**:
    - Trigger a scenario requiring user input (e.g., ambiguous request).
    - Verify `InterruptPayload` is generated.
    - Verify Streamlit UI renders the form/options correctly.
    - Verify submitting the form resumes the graph and completes the task.
