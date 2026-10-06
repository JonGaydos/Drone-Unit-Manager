# Stage 1: Build frontend
# node:20-alpine, pinned by digest alone. The digest is what is resolved, so
# carrying the tag as well only invites the two to disagree. To bump: re-resolve
# with `curl -s https://hub.docker.com/v2/repositories/library/node/tags/20-alpine | jq -r .digest`.
FROM node@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
# --ignore-scripts: nothing in the tree needs a lifecycle script. Only
# fsevents (macOS-only) and msw declare one, and msw is used through
# msw/node, which needs no generated service worker.
RUN npm ci --production=false --ignore-scripts
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + serve frontend
# python:3.12-slim, pinned by digest alone, matching the frontend stage above:
# the digest is what resolves, so carrying the tag as well only invites the two
# to disagree. Bump: re-resolve the library/python 3.12-slim digest.
FROM python@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

LABEL maintainer="JonGaydos"
LABEL org.opencontainers.image.title="Drone Unit Manager"
LABEL org.opencontainers.image.description="Self-hosted drone fleet management platform"
LABEL org.opencontainers.image.source="https://github.com/JonGaydos/Drone-Unit-Manager"

WORKDIR /app

# curl is for the HEALTHCHECK below. Reports are drawn with ReportLab and
# matplotlib's Agg backend, which need no system graphics libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.lock.txt ./
# --require-hashes refuses any package whose contents do not match the
# lock, and --only-binary refuses source distributions, so nothing runs a
# setup.py at build time. Every requirement resolves to a wheel.
RUN pip install --no-cache-dir --only-binary :all: --require-hashes -r requirements.lock.txt

# Copy backend code
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./static

# Copy entrypoint
COPY entrypoint.sh ./
# Everything the app writes lives under /app/data, so root buys nothing at
# runtime and costs a container escape being an escape as root.
#
# The container starts as root only so the entrypoint can give /app/data (a
# bind mount, which keeps the host's ownership) to the app's user, PUID:PGID
# (default 99:100, Unraid's nobody:users), and then drops to that user with
# setpriv before the app starts. A recreated or root-copied appdata folder
# therefore needs no manual chown. Started with --user, the entrypoint skips
# that and runs as given. setpriv comes with util-linux, in every Debian image;
# the check fails the build if that ever changes.
RUN chmod +x entrypoint.sh \
    && mkdir -p /app/data/uploads/documents /app/data/media_cache \
    && command -v setpriv

ENV DATA_DIR=/app/data
ENV DATABASE_URL=sqlite:////app/data/drone_unit_manager.db
# Unbuffered stdout/stderr so startup logs (including the fresh-install backup
# token) reach `docker logs` immediately instead of sitting in a block buffer.
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
