"""Workflow API Request/Response Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"  # HITL pending
    FAILED = "failed"


# === Request Schemas ===

class WorkflowRunRequest(BaseModel):
    """POST /api/workflow/run request"""
    user_input: str = Field(..., min_length=1, max_length=10000, description="User input text")
    file_content: Optional[str] = Field(None, max_length=100000, description="Uploaded file content")
    generation_preset: Literal["fast", "speed", "balanced", "quality"] = Field(
        default="balanced", description="Generation mode"
    )
    thread_id: Optional[str] = Field(None, description="Session ID (auto-generated if not provided)")
    refine_count: int = Field(default=0, ge=0, description="Refinement iteration count")
    previous_plan: Optional[str] = Field(None, description="Previous plan for refinement mode")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_input": "AI 기반 식단 관리 앱을 만들고 싶어요",
                "generation_preset": "balanced"
            }
        }
    }


class WorkflowResumeRequest(BaseModel):
    """POST /api/workflow/resume request (HITL resume)"""
    thread_id: str = Field(..., description="Session ID")
    resume_data: Dict[str, Any] = Field(..., description="User response data")
    generation_preset: Literal["fast", "speed", "balanced", "quality"] = Field(
        default="balanced", description="Generation mode"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "thread_id": "abc-123",
                "resume_data": {
                    "selected_option": {"title": "웹 앱", "description": "브라우저 기반 서비스"}
                },
                "generation_preset": "balanced"
            }
        }
    }


# === Response Schemas ===

class InterruptOption(BaseModel):
    """Interrupt option item"""
    title: str
    description: str


class InterruptPayloadResponse(BaseModel):
    """Interrupt payload for HITL"""
    type: str
    question: str
    options: List[InterruptOption] = []
    input_schema_name: Optional[str] = None


class TokenUsage(BaseModel):
    """Token usage statistics"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    estimated_cost_usd: float = 0.0
    estimated_cost_krw: float = 0.0


class WorkflowRunResponse(BaseModel):
    """POST /api/workflow/run response"""
    thread_id: str
    status: WorkflowStatus
    final_output: Optional[str] = None
    chat_summary: Optional[str] = None
    interrupt: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    step_history: List[Dict[str, Any]] = []
    error: Optional[str] = None
    token_usage: Optional[TokenUsage] = None  # [NEW] Token usage tracking

    model_config = {
        "json_schema_extra": {
            "example": {
                "thread_id": "abc-123",
                "status": "interrupted",
                "interrupt": {
                    "type": "option",
                    "question": "어떤 플랫폼을 원하시나요?",
                    "options": [
                        {"title": "웹 앱", "description": "브라우저 기반"},
                        {"title": "모바일 앱", "description": "iOS/Android"}
                    ]
                }
            }
        }
    }


class WorkflowStatusResponse(BaseModel):
    """GET /api/workflow/status/{thread_id} response"""
    thread_id: str
    status: WorkflowStatus
    current_step: Optional[str] = None
    step_history: List[Dict[str, Any]] = []
    has_pending_interrupt: bool = False
    result: Optional[Dict[str, Any]] = None  # 완료/중단 시 전체 상태 반환
    token_usage: Optional[TokenUsage] = None  # [NEW] Token usage tracking
