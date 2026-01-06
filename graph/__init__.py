# Graph 모듈
from graph.state import (
    PlanCraftState,
    PlanCraftInput,
    PlanCraftOutput,
    create_initial_state,
    update_state,
    safe_get,
    validate_state,
    ensure_dict,
)

# Lazy import for run_plancraft to avoid circular imports
# Use: from graph import run_plancraft
# Or: from graph.workflow import run_plancraft

__all__ = [
    # State
    "PlanCraftState",
    "PlanCraftInput",
    "PlanCraftOutput",
    "create_initial_state",
    "update_state",
    "safe_get",
    "validate_state",
    "ensure_dict",

    # Workflow Entry Point (lazy loaded)
    "run_plancraft",
]


def __getattr__(name: str):
    """Lazy import for avoiding circular imports"""
    if name == "run_plancraft":
        from graph.workflow import run_plancraft
        return run_plancraft

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
