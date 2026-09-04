# Stage 1: Build frontend
# Base pinned to digest for reproducible builds. To bump: re-resolve with
# `curl -s https://hub.docker.com/v2/repositories/library/node/tags/20-alpine | jq -r .digest`.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production=false
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + serve frontend
# Base pinned to digest. Bump: re-resolve library/python/tags/3.12-slim digest.
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

LABEL maintainer="JonGaydos"
LABEL org.opencontainers.image.title="Drone Unit Manager"
LABEL org.opencontainers.image.description="Self-hosted drone fleet management platform"
LABEL org.opencontainers.image.source="https://github.com/JonGaydos/Drone-Unit-Manager"

WORKDIR /app

# Install system dependencies for WeasyPrint (PDF generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libcairo2 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./static

# Copy entrypoint
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Create data directories
RUN mkdir -p /app/data/uploads/documents /app/data/media_cache

ENV DATA_DIR=/app/data
ENV DATABASE_URL=sqlite:////app/data/drone_unit_manager.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
