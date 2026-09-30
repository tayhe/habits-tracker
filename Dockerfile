FROM python:3.12-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install tzdata for container timezone support
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# Create non-root user matching host permissions
ARG UID=1002
ARG GID=1002
RUN groupadd -g ${GID} appuser && useradd -m -u ${UID} -g appuser appuser


# Set working directory
WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY backend/ backend/
COPY frontend/ frontend/

# Ensure permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment
ENV TZ=Asia/Shanghai
ENV PYTHONPATH=.
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 15000

CMD ["uv", "run", "--no-dev", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "15000"]


