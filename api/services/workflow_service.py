"""Workflow Service - Business logic layer wrapping run_plancraft"""
import uuid
import asyncio
import logging
from typing import Optional, Dict, Any

from api.schemas.workflow import (
    WorkflowRunResponse,
    WorkflowStatus,
    WorkflowStatusResponse,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class WorkflowService:
    """Workflow business logic service"""

    def run_background_sync(
        self,
        user_input: str,
        thread_id: str,
        file_content: Optional[str] = None,
        generation_preset: str = "balanced",
        refine_count: int = 0,
        previous_plan: Optional[str] = None,
    ) -> None:
        """
        Execute workflow in background (Synchronous - for FastAPI BackgroundTasks)

        Note: BackgroundTasks expects sync callables, not coroutines.
        """
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        token_callback = TokenTrackingCallback()

        try:
            logger.info(f"[Workflow] Starting background execution: {thread_id}")
            run_plancraft(
                user_input=user_input,
                file_content=file_content,
                generation_preset=generation_preset,
                thread_id=thread_id,
                refine_count=refine_count,
                previous_plan=previous_plan,
                callbacks=[token_callback],
            )
            logger.info(f"[Workflow] Background execution completed: {thread_id}")
            logger.debug(f"[Workflow] Token usage: {token_callback.get_usage_summary()}")
        except Exception as e:
            logger.error(f"[Workflow] Background execution failed: {thread_id} - {e}", exc_info=True)
            raise

    def resume_background_sync(
        self,
        thread_id: str,
        resume_data: Dict[str, Any],
        generation_preset: str = "balanced",
    ) -> None:
        """
        Resume workflow in background (Synchronous - for FastAPI BackgroundTasks)
        """
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        token_callback = TokenTrackingCallback()

        try:
            logger.info(f"[Workflow] Resuming background execution: {thread_id}")
            run_plancraft(
                user_input="",
                thread_id=thread_id,
                resume_command={"resume": resume_data},
                generation_preset=generation_preset,
                callbacks=[token_callback],
            )
            logger.info(f"[Workflow] Background resume completed: {thread_id}")
        except Exception as e:
            logger.error(f"[Workflow] Background resume failed: {thread_id} - {e}", exc_info=True)
            raise

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

        token_callback = TokenTrackingCallback()

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

        # Integrate token usage into result
        if result and isinstance(result, dict):
            result["token_usage"] = token_callback.get_usage_summary()

        return self._convert_to_response(thread_id, result)

    async def resume(
        self,
        thread_id: str,
        resume_data: Dict[str, Any],
        generation_preset: str = "balanced",
    ) -> WorkflowRunResponse:
        """Resume HITL interrupt (Wait for result)"""
        from graph.workflow import run_plancraft
        from utils.streamlit_callback import TokenTrackingCallback

        token_callback = TokenTrackingCallback()

        result = await asyncio.to_thread(
            run_plancraft,
            user_input="",
            thread_id=thread_id,
            resume_command={"resume": resume_data},
            generation_preset=generation_preset,
            callbacks=[token_callback],
        )

        # Integrate token usage into result
        if result and isinstance(result, dict):
            result["token_usage"] = token_callback.get_usage_summary()

        return self._convert_to_response(thread_id, result)

    async def get_status(self, thread_id: str) -> Optional[WorkflowStatusResponse]:
        """Get workflow status with improved error handling"""
        from graph.workflow import app

        config = {"configurable": {"thread_id": thread_id}}

        try:
            snapshot = app.get_state(config)
        except KeyError:
            # Thread not found - expected case
            logger.debug(f"[Workflow] Thread not found: {thread_id}")
            return None
        except Exception as e:
            # Unexpected error - log and re-raise
            logger.error(f"[Workflow] Error getting status for {thread_id}: {e}", exc_info=True)
            raise

        if not snapshot or not snapshot.values:
            return None

        state = snapshot.values

        # Check for interrupts (두 가지 패턴 지원)
        interrupt_value = None
        if snapshot.next and snapshot.tasks:
            next_node = snapshot.next[0] if snapshot.next else None

            # Pattern 1: interrupt_before 패턴 (option_pause 노드 전에 interrupt)
            if next_node == "option_pause":
                # State에서 interrupt payload 구성
                interrupt_value = {
                    "type": "option_selector",
                    "question": state.get("option_question", "추가 정보가 필요합니다."),
                    "options": state.get("options", []),
                    "node_ref": "option_pause",
                    "data": {
                        "user_input": state.get("user_input", ""),
                        "topic": state.get("analysis", {}).get("topic", "") if state.get("analysis") else "",
                        "clarification_questions": state.get("analysis", {}).get("clarification_questions", []) if state.get("analysis") else [],
                    }
                }
            # Pattern 2: 노드 내부 interrupt() 호출 (기존 방식)
            elif hasattr(snapshot.tasks[0], "interrupts") and snapshot.tasks[0].interrupts:
                interrupt_value = snapshot.tasks[0].interrupts[0].value

        has_interrupt = bool(interrupt_value)
        status = self._determine_status(state, has_interrupt)

        # Prepare result dict if finished or interrupted
        result_data = None
        if status in [WorkflowStatus.COMPLETED, WorkflowStatus.INTERRUPTED, WorkflowStatus.FAILED]:
            result_data = dict(state)
            if interrupt_value:
                result_data["__interrupt__"] = interrupt_value
            if status == WorkflowStatus.FAILED and not result_data.get("error"):
                result_data["error"] = "Unknown error occurred"

        # Extract token usage if available
        token_usage = self._extract_token_usage(state.get("token_usage"))

        return WorkflowStatusResponse(
            thread_id=thread_id,
            status=status,
            current_step=state.get("current_step"),
            step_history=state.get("step_history", []),
            has_pending_interrupt=has_interrupt,
            result=result_data,
            token_usage=token_usage,
        )

    def _extract_token_usage(self, usage_data: Optional[Dict]) -> Optional[TokenUsage]:
        """Extract and validate token usage data"""
        if not usage_data:
            return None

        try:
            return TokenUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                llm_calls=usage_data.get("llm_calls", 0),
                estimated_cost_usd=usage_data.get("estimated_cost_usd", 0.0),
                estimated_cost_krw=usage_data.get("estimated_cost_krw", 0.0),
            )
        except Exception as e:
            logger.warning(f"[Workflow] Failed to extract token usage: {e}")
            return None

    def _convert_to_response(self, thread_id: str, result: dict) -> WorkflowRunResponse:
        """Convert result dict to WorkflowRunResponse"""
        if not result:
            result = {}

        interrupt = result.get("__interrupt__")

        if interrupt:
            status = WorkflowStatus.INTERRUPTED
        elif result.get("error"):
            status = WorkflowStatus.FAILED
        elif result.get("final_output"):
            status = WorkflowStatus.COMPLETED
        else:
            status = WorkflowStatus.RUNNING

        token_usage = self._extract_token_usage(result.get("token_usage"))

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
