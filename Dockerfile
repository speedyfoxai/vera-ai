# Vera-AI Dockerfile
# Multi-stage build with configurable UID/GID and timezone
#
# Build arguments:
#   APP_UID: User ID for appuser (default: 999)
#   APP_GID: Group ID for appgroup (default: 999)

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Build arguments for UID/GID
ARG APP_UID=999
ARG APP_GID=999

# Create group and user with specified UID/GID
RUN groupadd -g ${APP_GID} appgroup &&     useradd -u ${APP_UID} -g appgroup -r -m -s /bin/bash appuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Create directories for mounted volumes
RUN mkdir -p /app/config /app/prompts /app/logs &&     chown -R ${APP_UID}:${APP_GID} /app

# Copy application code
COPY app/ ./app/

# Copy default config and prompts (can be overridden by volume mounts)
COPY config/config.toml /app/config/config.toml
COPY prompts/curator_prompt.md /app/prompts/curator_prompt.md
COPY prompts/systemprompt.md /app/prompts/systemprompt.md

# Create symlink for config backward compatibility
RUN ln -sf /app/config/config.toml /app/config.toml

# Set ownership
RUN chown -R ${APP_UID}:${APP_GID} /app && chmod -R u+rw /app

# Runtime environment variables
ENV TZ=UTC

EXPOSE 11434

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:11434/')" || exit 1

# Switch to non-root user
USER appuser

ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "11434"]
