# Multi-stage Docker build using uv for ultra-fast, deterministic dependency resolution
FROM ghcr.io/astral-sh/uv:latest AS uv_bin
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy uv from official binary image
COPY --from=uv_bin /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications and lockfile
COPY pyproject.toml uv.lock README.md ./

# Create virtual environment and install production dependencies with uv sync
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
RUN uv sync --frozen --no-dev

# Production runtime stage
FROM python:3.12-slim AS runner

WORKDIR /app

# Run as non-root user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8001 50051

CMD ["python", "-m", "app.main"]
