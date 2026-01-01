# =============================================================================
# PlanCraft Agent - Production Dockerfile
# Multi-Agent AI 기획서 생성 서비스 (v2.1)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base Image
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Dependencies
# -----------------------------------------------------------------------------
FROM base AS dependencies

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Python 의존성 설치 (캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 3: Application
# -----------------------------------------------------------------------------
FROM dependencies AS app

# 애플리케이션 코드 복사
# .dockerignore에서 불필요한 파일 제외됨
COPY agents/ ./agents/
COPY graph/ ./graph/
COPY prompts/ ./prompts/
COPY tools/ ./tools/
COPY utils/ ./utils/
COPY rag/ ./rag/
COPY app.py .
COPY README.md .

# 필요한 디렉토리 생성
RUN mkdir -p logs outputs streamlit_logs

# 비루트 사용자 생성 (보안 강화)
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Streamlit 설정
RUN mkdir -p ~/.streamlit && \
    echo '[server]' > ~/.streamlit/config.toml && \
    echo 'headless = true' >> ~/.streamlit/config.toml && \
    echo 'enableCORS = false' >> ~/.streamlit/config.toml && \
    echo 'enableXsrfProtection = false' >> ~/.streamlit/config.toml && \
    echo '' >> ~/.streamlit/config.toml && \
    echo '[browser]' >> ~/.streamlit/config.toml && \
    echo 'gatherUsageStats = false' >> ~/.streamlit/config.toml

# 포트 노출
EXPOSE 8501

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 실행 명령
CMD ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
