"""PlanCraft FastAPI Application"""
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import workflow_router

# Global server instance for thread management
_api_server = None
_api_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    yield


app = FastAPI(
    title="PlanCraft API",
    description="Multi-Agent Orchestration & HITL Planning Assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(workflow_router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "plancraft-api"}


def start_api_server(host: str = "127.0.0.1", port: int = 8000, timeout: float = 10.0) -> threading.Thread:
    """
    Start API server in background thread

    Args:
        host: Server host address
        port: Server port number
        timeout: Max seconds to wait for server startup

    Returns:
        Thread running the server
    """
    global _api_server, _api_thread

    # Prevent duplicate server starts
    if _api_thread is not None and _api_thread.is_alive():
        # Verify server is responding
        import httpx
        try:
            resp = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
            if resp.status_code == 200:
                print(f"[API] Server already running on {host}:{port}")
                return _api_thread
        except Exception:
            pass  # Server thread alive but not responding, restart

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    _api_server = uvicorn.Server(config)

    def run_server():
        _api_server.run()

    _api_thread = threading.Thread(target=run_server, daemon=True)
    _api_thread.start()

    # Wait for server to actually start (health check)
    import httpx
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            resp = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
            if resp.status_code == 200:
                print(f"[API] Server started successfully on {host}:{port}")
                return _api_thread
        except Exception:
            pass
        time.sleep(0.3)

    print(f"[API] WARNING: Server may not be ready after {timeout}s")
    return _api_thread


def stop_api_server():
    """Stop the API server"""
    global _api_server
    if _api_server:
        _api_server.should_exit = True


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
