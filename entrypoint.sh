#!/bin/bash
set -e

# DATA_DIR is set in the Dockerfile and can be overridden. Read it once here so
# every path below follows it rather than hardcoding the default in five places.
DATA_DIR="${DATA_DIR:-/app/data}"

echo "========================================="
echo "  Drone Unit Manager"
echo "  Starting up..."
echo "========================================="

# Ensure data directories exist. This is the first thing that touches the data
# volume, so it is where a permissions problem surfaces. The container runs as a
# normal user and /app/data is a bind mount that keeps the host's ownership, so
# say plainly what is wrong rather than letting a bare mkdir error stand.
if ! mkdir -p "$DATA_DIR/uploads/documents" "$DATA_DIR/media_cache" 2>/dev/null; then
    echo "ERROR: cannot write to $DATA_DIR." >&2
    echo "This container runs as uid $(id -u), gid $(id -g)." >&2
    echo "The mapped host directory must be writable by that user. On Unraid," >&2
    echo "add '--user 99:100' to Extra Parameters (appdata is nobody:users)," >&2
    echo "or chown the directory to 1000:1000. See docs/upgrading.md." >&2
    exit 1
fi

# Generate secret key if not provided
if [[ -z "${SECRET_KEY}" || "${SECRET_KEY}" = "change-me-in-production" ]]; then
    if [[ ! -f "$DATA_DIR/.secret_key" ]]; then
        python -c "import secrets; print(secrets.token_hex(32))" > "$DATA_DIR/.secret_key"
        echo "Generated new secret key"
    fi
    SECRET_KEY="$(cat "$DATA_DIR/.secret_key")"
    export SECRET_KEY
fi

echo "Data directory: ${DATA_DIR}"
echo "Database: ${DATABASE_URL}"
echo "========================================="

# Run the application
exec "$@"
