"""PlanCraft FastAPI Application"""
import os
import logging
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import workflow_router

logger = logging.getLogger(__name__)

# Thread-safe global state
_api_lock = threading.Lock()
_api_server = None
_api_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler with resource management"""
    # JSON 로깅 설정
    from utils.logging_config import setup_logging
    setup_logging(level="INFO", json_format=True)
    
    logger.info("[API] FastAPI server starting...")
    yield
    logger.info("[API] FastAPI server shutting down...")


app = FastAPI(
    title="PlanCraft API",
    description="Multi-Agent Orchestration & HITL Planning Assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - configurable via environment
ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8501,http://127.0.0.1:8501,http://localhost:8624,http://127.0.0.1:8624"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Include routers
app.include_router(workflow_router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "plancraft-api"}


def start_api_server(host: str = "127.0.0.1", port: int = 8000, timeout: float = 10.0) -> threading.Thread:
    """
    Start API server in background thread (Thread-safe)

    Args:
        host: Server host address
        port: Server port number
        timeout: Max seconds to wait for server startup

    Returns:
        Thread running the server
    """
    global _api_server, _api_thread

    with _api_lock:
        # Check if server is already running
        if _api_thread is not None and _api_thread.is_alive():
            import httpx
            try:
                resp = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
                if resp.status_code == 200:
                    logger.info(f"[API] Server already running on {host}:{port}")
                    return _api_thread
            except Exception:
                logger.warning("[API] Server thread alive but not responding, restarting...")

        # Create server config
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        _api_server = uvicorn.Server(config)

        def run_server():
            try:
                _api_server.run()
            except Exception as e:
                logger.error(f"[API] Server error: {e}")

        _api_thread = threading.Thread(target=run_server, daemon=True, name="FastAPI-Server")
        _api_thread.start()

    # Wait for server with exponential backoff (outside lock)
    import httpx
    start_time = time.time()
    delay = 0.1
    max_delay = 1.0

    while time.time() - start_time < timeout:
        try:
            resp = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
            if resp.status_code == 200:
                elapsed = time.time() - start_time
                logger.info(f"[API] Server started successfully on {host}:{port} ({elapsed:.2f}s)")
                return _api_thread
        except Exception:
            pass

        time.sleep(delay)
        delay = min(delay * 1.5, max_delay)

    logger.warning(f"[API] Server may not be ready after {timeout}s")
    return _api_thread


def stop_api_server():
    """Stop the API server gracefully"""
    global _api_server

    with _api_lock:
        if _api_server:
            logger.info("[API] Stopping server...")
            _api_server.should_exit = True


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
