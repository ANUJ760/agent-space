# ==============================================================================
# Agent Space - Production Frontend Dockerfile (Multi-stage & Hardened)
# ==============================================================================
# Security features:
# - Multi-stage build (deps -> builder -> runner)
# - Minimal Alpine Linux base image (node:20-alpine)
# - Pinned dependencies via npm ci and lockfile
# - Dedicated unprivileged system user/group (nextjs:10001)
# - Non-root execution
# - Active health check endpoint validation
# - No secrets or sensitive configuration baked in
# ==============================================================================

# --- Stage 1: Install dependencies ---
FROM node:20-alpine AS deps

# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy dependency manifests
COPY apps/frontend/package.json ./package.json
COPY apps/frontend/package-lock.json* ./package-lock.json

# Install dependencies strictly from lockfile
RUN if [ -f package-lock.json ]; then npm ci --ignore-scripts; else npm install --ignore-scripts; fi

# --- Stage 2: Build Next.js application ---
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY apps/frontend ./

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN npm run build

# --- Stage 3: Hardened Production Runner ---
FROM node:20-alpine AS runner

WORKDIR /app

# Security hardening: Create non-root system group and user
RUN addgroup --system --gid 10001 nodejs && \
    adduser --system --uid 10001 nextjs

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Copy built application assets with restricted permissions
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json

# Switch to unprivileged user
USER nextjs

# Expose Next.js frontend port
EXPOSE 3000

# Health check using Node stdlib http client
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000', (r) => {if (r.statusCode < 500) process.exit(0); else process.exit(1);})" || exit 1

CMD ["npm", "start"]
