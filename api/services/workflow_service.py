"""Workflow Service - Business logic layer wrapping run_plancraft"""
import uuid
import asyncio
from typing import Optional, Dict, Any

from api.schemas.workflow import (
    WorkflowRunResponse,
    WorkflowStatus,
    WorkflowStatusResponse,
    TokenUsage,
)


class WorkflowService:
    """Workflow business logic service"""

    async def run_background(
        self,
        user_input: str,
        thread_id: str,
        file_content: Optional[str] = None,
        generation_preset: str = "balanced",
        refine_count: int = 0,
        previous_plan: Optional[str] = None,
    ):
        """Execute workflow in background (Fire-and-Forget)"""
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        # [NEW] Token tracking callback for API context
        token_callback = TokenTrackingCallback()

        # run_plancraft saves state to checkpointer automatically
        await asyncio.to_thread(
            run_plancraft,
            user_input=user_input,
            file_content=file_content,
            generation_preset=generation_preset,
            thread_id=thread_id,
            refine_count=refine_count,
            previous_plan=previous_plan,
            callbacks=[token_callback],
        )

    async def resume_background(
        self,
        thread_id: str,
        resume_data: Dict[str, Any],
    ):
        """Resume workflow in background"""
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        # [NEW] Token tracking callback for API context
        token_callback = TokenTrackingCallback()

        await asyncio.to_thread(
            run_plancraft,
            user_input="",
            thread_id=thread_id,
            resume_command={"resume": resume_data},
            callbacks=[token_callback],
        )

    async def run(
        self,
        user_input: str,
        file_content: Optional[str] = None,
        generation_preset: str = "balanced",
        thread_id: Optional[str] = None,
        refine_count: int = 0,
        previous_plan: Optional[str] = None,
    ) -> WorkflowRunResponse:
        """Execute workflow (Wait for result)"""
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        if not thread_id:
            thread_id = str(uuid.uuid4())

        # [NEW] Token tracking callback for API context
        token_callback = TokenTrackingCallback()

        # run_plancraft is synchronous, use asyncio.to_thread
        result = await asyncio.to_thread(
            run_plancraft,
            user_input=user_input,
            file_content=file_content,
            generation_preset=generation_preset,
            thread_id=thread_id,
            refine_count=refine_count,
            previous_plan=previous_plan,
            callbacks=[token_callback],
        )

        return self._convert_to_response(thread_id, result)

    async def resume(
        self,
        thread_id: str,
        resume_data: Dict[str, Any],
    ) -> WorkflowRunResponse:
        """Resume HITL interrupt (Wait for result)"""
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        # [NEW] Token tracking callback for API context
        token_callback = TokenTrackingCallback()

        result = await asyncio.to_thread(
            run_plancraft,
            user_input="",  # Not needed for resume
            thread_id=thread_id,
            resume_command={"resume": resume_data},
            callbacks=[token_callback],
        )

        return self._convert_to_response(thread_id, result)

    async def get_status(self, thread_id: str) -> Optional[WorkflowStatusResponse]:
        """Get workflow status"""
        from graph.workflow import app

        config = {"configurable": {"thread_id": thread_id}}

        try:
            snapshot = app.get_state(config)
        except Exception:
            return None

        if not snapshot or not snapshot.values:
            return None

        state = snapshot.values
        
        # Check for interrupts
        interrupt_value = None
        if snapshot.next and snapshot.tasks:
            if hasattr(snapshot.tasks[0], "interrupts") and snapshot.tasks[0].interrupts:
                 interrupt_value = snapshot.tasks[0].interrupts[0].value

        has_interrupt = bool(interrupt_value)
        status = self._determine_status(state, has_interrupt)
        
        # Prepare result dict if finished or interrupted
        result_data = None
        if status in [WorkflowStatus.COMPLETED, WorkflowStatus.INTERRUPTED, WorkflowStatus.FAILED]:
            result_data = dict(state)
            if interrupt_value:
                result_data["__interrupt__"] = interrupt_value
            # Add error info if failed
            if status == WorkflowStatus.FAILED and not result_data.get("error"):
                 result_data["error"] = "Unknown error occurred"

        # [NEW] Extract token usage if available
        token_usage = None
        if state.get("token_usage"):
            usage_data = state["token_usage"]
            token_usage = TokenUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                llm_calls=usage_data.get("llm_calls", 0),
                estimated_cost_usd=usage_data.get("estimated_cost_usd", 0.0),
                estimated_cost_krw=usage_data.get("estimated_cost_krw", 0.0),
            )

        return WorkflowStatusResponse(
            thread_id=thread_id,
            status=status,
            current_step=state.get("current_step"),
            step_history=state.get("step_history", []),
            has_pending_interrupt=has_interrupt,
            result=result_data,
            token_usage=token_usage,
        )

    def _convert_to_response(self, thread_id: str, result: dict) -> WorkflowRunResponse:
        """Convert result dict to WorkflowRunResponse"""
        interrupt = result.get("__interrupt__")

        if interrupt:
            status = WorkflowStatus.INTERRUPTED
        elif result.get("error"):
            status = WorkflowStatus.FAILED
        elif result.get("final_output"):
            status = WorkflowStatus.COMPLETED
        else:
            status = WorkflowStatus.RUNNING

        # [NEW] Extract token usage if available
        token_usage = None
        if result.get("token_usage"):
            usage_data = result["token_usage"]
            token_usage = TokenUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                llm_calls=usage_data.get("llm_calls", 0),
                estimated_cost_usd=usage_data.get("estimated_cost_usd", 0.0),
                estimated_cost_krw=usage_data.get("estimated_cost_krw", 0.0),
            )

        return WorkflowRunResponse(
            thread_id=thread_id,
            status=status,
            final_output=result.get("final_output"),
            chat_summary=result.get("chat_summary"),
            interrupt=interrupt,
            analysis=result.get("analysis"),
            step_history=result.get("step_history", []),
            error=result.get("error"),
            token_usage=token_usage,
        )

    def _determine_status(self, state: dict, has_interrupt: bool) -> WorkflowStatus:
        """Determine workflow status from state"""
        if has_interrupt:
            return WorkflowStatus.INTERRUPTED
        if state.get("error"):
            return WorkflowStatus.FAILED
        if state.get("final_output"):
            return WorkflowStatus.COMPLETED
        return WorkflowStatus.RUNNING
