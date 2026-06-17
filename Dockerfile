# Use a Python image with uv pre-installed (Debian Bookworm slim)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set working directory in the container
WORKDIR /app

# Prevent Python from buffering stdout and stderr to ensure logs are flushed immediately
ENV PYTHONUNBUFFERED=1

# Enable bytecode compilation for faster imports and startup
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since we mount a volume for cache
ENV UV_LINK_MODE=copy

# Omit development dependencies (e.g. pytest, ruff, radon) in production
ENV UV_NO_DEV=1

# 1. Install dependencies first (leverage Docker layer caching)
# We bind mount pyproject.toml and uv.lock so they are available without copying the entire source code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# 2. Copy the project source files into the container
COPY . /app

# 3. Complete the project sync
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Ensure virtual environment executables (like uvicorn, evenezer, evenezer-bot) are directly accessible
ENV PATH="/app/.venv/bin:$PATH"

# Create a non-root user and group, then grant ownership of /app
RUN groupadd -g 1001 appgroup && \
    useradd -r -u 1001 -g appgroup -d /app appuser && \
    chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Default CMD (can be overridden in docker-compose.yml)
CMD ["evenezer"]
