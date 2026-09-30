# ==============================================================================
# Agent Space — Production Dockerfile (Multi-Stage & Hardened)
# ==============================================================================
# Targets:
# - backend (default): Production FastAPI REST API & WebSocket server
# - worker: Temporal durable workflow & LangGraph agent loop worker
# - frontend: Next.js 14 web application & Three.js 3D workspace
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Python Builder (Compiles extensions & installs pinned dependencies)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS python-builder

WORKDIR /build

# Install build dependencies required for compiling extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment and install pinned requirements
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY requirements-prod.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-prod.txt


# ------------------------------------------------------------------------------
# Stage 2: Backend Runtime (Default Target)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS backend

# Security hardening: Dedicated unprivileged system user and group (UID 10001)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /sbin/nologin -M appuser

WORKDIR /app

# Copy isolated virtual environment from builder stage
COPY --from=python-builder --chown=appuser:appuser /app/.venv /app/.venv

# Environment configuration
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PYTHONPATH=/app

# Copy application modules and configurations
COPY --chown=appuser:appuser apps /app/apps
COPY --chown=appuser:appuser agents /app/agents
COPY --chown=appuser:appuser packages /app/packages
COPY --chown=appuser:appuser alembic.ini /app/alembic.ini
COPY --chown=appuser:appuser pyproject.toml /app/pyproject.toml

# Switch to unprivileged user
USER 10001:10001

# Expose backend API port
EXPOSE 8000

# Health check using Python stdlib (no external dependencies)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Launch production ASGI application via factory
ENTRYPOINT ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]


# ------------------------------------------------------------------------------
# Stage 3: Worker Runtime (Target: worker)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS worker

RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /sbin/nologin -M appuser

WORKDIR /app

COPY --from=python-builder --chown=appuser:appuser /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    PYTHONPATH=/app

COPY --chown=appuser:appuser apps /app/apps
COPY --chown=appuser:appuser agents /app/agents
COPY --chown=appuser:appuser packages /app/packages
COPY --chown=appuser:appuser pyproject.toml /app/pyproject.toml

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys; sys.exit(0)" || exit 1

ENTRYPOINT ["python", "-m", "app.temporal.worker"]


# ------------------------------------------------------------------------------
# Stage 4: Frontend Builder (Target: frontend-builder)
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy root workspace and frontend manifests
COPY package.json package-lock.json* ./
COPY apps/frontend/package.json ./apps/frontend/package.json

RUN npm ci --ignore-scripts

COPY apps/frontend ./apps/frontend

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN npm run build --workspace=@agent-space/frontend


# ------------------------------------------------------------------------------
# Stage 5: Frontend Runtime (Target: frontend)
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /app

RUN addgroup --system --gid 10001 nodejs && \
    adduser --system --uid 10001 nextjs

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

COPY --from=frontend-builder --chown=nextjs:nodejs /app/apps/frontend/public ./public
COPY --from=frontend-builder --chown=nextjs:nodejs /app/apps/frontend/.next ./.next
COPY --from=frontend-builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=frontend-builder --chown=nextjs:nodejs /app/apps/frontend/package.json ./package.json

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000', (r) => {if (r.statusCode < 500) process.exit(0); else process.exit(1);})" || exit 1

CMD ["npm", "start"]
