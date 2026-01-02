"""Workflow API Router"""
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.schemas.workflow import (
    WorkflowRunRequest,
    WorkflowResumeRequest,
    WorkflowRunResponse,
    WorkflowStatusResponse,
    WorkflowStatus,  # [FIX] Missing import
)
from api.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest, background_tasks: BackgroundTasks):
    """
    Execute PlanCraft workflow (Async Background)

    - Start new session or reuse existing session
    - Returns immediately with status 'running'
    - Client should poll /status/{thread_id} for updates
    """
    service = WorkflowService()
    # Start workflow in background
    background_tasks.add_task(
        service.run_background,
        user_input=request.user_input,
        file_content=request.file_content,
        generation_preset=request.generation_preset,
        thread_id=request.thread_id,
        refine_count=request.refine_count,
        previous_plan=request.previous_plan,
    )
    
    # Return immediate response
    return WorkflowRunResponse(
        thread_id=request.thread_id or "pending", # service.run_background handles internal logic, but here we need ID. 
        # Note: service.run_background logic might need adjustment to handle ID generation BEFORE task.
        # Let's adjust service first or handle UUID here if none.
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
    service = WorkflowService()
    background_tasks.add_task(
        service.resume_background,
        thread_id=request.thread_id,
        resume_data=request.resume_data,
    )
    
    return WorkflowRunResponse(
        thread_id=request.thread_id,
        status=WorkflowStatus.RUNNING
    )


@router.get("/status/{thread_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(thread_id: str):
    """
    Get workflow status

    - Current step, history, interrupt pending status
    """
    service = WorkflowService()
    result = await service.get_status(thread_id)
    if not result:
        raise HTTPException(status_code=404, detail="Thread not found")
    return result
