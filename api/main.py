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


def start_api_server(host: str = "127.0.0.1", start_port: int = 8000, max_retries: int = 5, timeout: float = 10.0) -> int:
    """
    Start API server in background thread (Thread-safe)
    Finds available port automatically.

    Args:
        host: Server host address
        start_port: Starting port number
        max_retries: Number of ports to try
        timeout: Max seconds to wait for server startup

    Returns:
        int: The port number the server is running on
    """
    global _api_server, _api_thread

    import httpx
    import socket

    for port in range(start_port, start_port + max_retries + 1):
        # 1. Check if port is already running a VALID server
        try:
            resp = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("service") == "plancraft-api":
                    logger.info(f"[API] Found active valid server on {host}:{port}")
                    return port
                else:
                    logger.warning(f"[API] Port {port} occupied by stale/unknown service. Skipping.")
                    continue
        except Exception:
            # Not responding - might be free or dead
            pass

        # 2. Check if port is TCP occupied (but not responding to HTTP above)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) == 0:
                logger.warning(f"[API] Port {port} is in use (TCP). Skipping.")
                continue

        # 3. Port seems free - Attempt to start
        logger.info(f"[API] Attempting to start server on port {port}...")

        with _api_lock:
            # uvicorn 버전 호환성: install_signal_handlers는 0.19+ 필요
            config_kwargs = {
                "app": app,
                "host": host,
                "port": port,
                "log_level": "warning",
                "access_log": False,
                "lifespan": "off",
            }
            # 선택적 파라미터 (구버전 uvicorn 호환)
            try:
                # uvicorn 0.19+ 에서 지원
                config = uvicorn.Config(**config_kwargs, install_signal_handlers=False, ws="none")
            except TypeError:
                # 구버전 uvicorn 폴백
                logger.warning("[API] Old uvicorn version detected, using basic config")
                config = uvicorn.Config(**config_kwargs)
            _api_server = uvicorn.Server(config)

            def run_server():
                try:
                    _api_server.run()
                except Exception as e:
                    logger.error(f"[API] Server thread error on {port}: {e}")

            _api_thread = threading.Thread(target=run_server, daemon=True, name=f"FastAPI-{port}")
            _api_thread.start()

        # 4. Wait/Verify startup
        start_time = time.time()
        delay = 0.2
        
        while time.time() - start_time < timeout:
            try:
                resp = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
                if resp.status_code == 200 and resp.json().get("service") == "plancraft-api":
                    logger.info(f"[API] Server started successfully on {host}:{port}")
                    return port
            except Exception:
                pass
            
            if not _api_thread.is_alive():
                 logger.error(f"[API] Server thread died immediately on {port}")
                 break
            
            time.sleep(delay)
            
        # If we reached here, this port failed to start in time or thread died.
        # Stop specific server instance (if running) and try next port
        if _api_server:
            _api_server.should_exit = True
        logger.warning(f"[API] Failed to start on {port}, trying next...")
        time.sleep(1.0)

    raise RuntimeError(f"Could not start API server on any port from {start_port} to {start_port + max_retries}")


def stop_api_server():
    """Stop the API server gracefully"""
    global _api_server

    with _api_lock:
        if _api_server:
            logger.info("[API] Stopping server...")
            _api_server.should_exit = True


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
