"""Workflow API Router"""
import uuid
import asyncio
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.schemas.workflow import (
    WorkflowRunRequest,
    WorkflowResumeRequest,
    WorkflowRunResponse,
    WorkflowStatusResponse,
    WorkflowStatus,
)
from api.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest, background_tasks: BackgroundTasks):
    """
    Execute PlanCraft workflow (Async Background)

    - Start new session or reuse existing session
    - Returns immediately with status 'running'
    - Client should poll /status/{thread_id} for updates
    """
    # Generate thread_id if not provided
    thread_id = request.thread_id or str(uuid.uuid4())

    # Validate thread_id format
    if len(thread_id) > 36:
        raise HTTPException(
            status_code=400,
            detail="thread_id must be 36 characters or less"
        )

    service = WorkflowService()

    # Add sync background task
    background_tasks.add_task(
        service.run_background_sync,
        user_input=request.user_input,
        thread_id=thread_id,
        file_content=request.file_content,
        generation_preset=request.generation_preset,
        refine_count=request.refine_count,
        previous_plan=request.previous_plan,
    )

    logger.info(f"[API] Workflow started: {thread_id}")

    return WorkflowRunResponse(
        thread_id=thread_id,
        status=WorkflowStatus.RUNNING,
        step_history=[],
        final_output=None
    )


@router.post("/resume", response_model=WorkflowRunResponse)
async def resume_workflow(request: WorkflowResumeRequest, background_tasks: BackgroundTasks):
    """
    Resume HITL interrupt (Async Background)

    - Continue workflow with user response in background
    - Returns immediately with status 'running'
    """
    if not request.resume_data:
        raise HTTPException(
            status_code=400,
            detail="resume_data cannot be empty"
        )

    service = WorkflowService()

    # Verify thread exists and is in proper state
    try:
        current_status = await service.get_status(request.thread_id)
        if not current_status:
            raise HTTPException(
                status_code=404,
                detail=f"Thread not found: {request.thread_id}"
            )
        if current_status.status != WorkflowStatus.INTERRUPTED:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot resume: thread is {current_status.status.value}, not interrupted"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error verifying thread: {e}")
        raise HTTPException(status_code=500, detail="Error verifying thread state")

    # Add sync background task
    background_tasks.add_task(
        service.resume_background_sync,
        thread_id=request.thread_id,
        resume_data=request.resume_data,
        generation_preset=request.generation_preset,
    )

    logger.info(f"[API] Workflow resumed: {request.thread_id}")

    return WorkflowRunResponse(
        thread_id=request.thread_id,
        status=WorkflowStatus.RUNNING,
        step_history=current_status.step_history or []
    )


@router.get("/status/{thread_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(thread_id: str):
    """
    Get workflow status

    - Returns current step, history, interrupt pending status
    - 404: Thread not found
    - 400: Invalid thread_id format
    """
    # Validate thread_id format
    if not thread_id or len(thread_id) > 36:
        raise HTTPException(
            status_code=400,
            detail="Invalid thread_id: must be non-empty and 36 chars or less"
        )

    try:
        service = WorkflowService()
        result = await asyncio.wait_for(
            service.get_status(thread_id),
            timeout=10.0
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No workflow found for thread_id: {thread_id}"
            )

        return result

    except asyncio.TimeoutError:
        logger.error(f"[API] Status check timeout: {thread_id}")
        raise HTTPException(
            status_code=504,
            detail="Status check timed out"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error getting status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve workflow status"
        )
