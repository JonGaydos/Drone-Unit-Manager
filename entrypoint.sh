#!/bin/bash
set -e

# DATA_DIR is set in the Dockerfile and can be overridden. Read it once here so
# every path below follows it rather than hardcoding the default in five places.
DATA_DIR="${DATA_DIR:-/app/data}"

# Started as root (no --user): give the data directory to the app's user, then
# drop to that user before anything else runs, so the app itself never runs as
# root. This is what lets a deleted, recreated or root-copied appdata folder
# start without a manual chown. PUID/PGID choose the user; the default 99:100 is
# Unraid's nobody:users, the owner of everything else in appdata. Started with
# --user, none of this runs and the checks below apply as before. PUID=0 keeps
# root deliberately (and must skip this, or the re-exec below would loop).
PUID="${PUID:-99}"
PGID="${PGID:-100}"
if [[ "$(id -u)" = "0" && "$PUID" != "0" ]]; then
    mkdir -p "$DATA_DIR/uploads/documents" "$DATA_DIR/media_cache"
    # Only what is not already theirs, so a large data folder is not rewritten
    # on every start.
    find "$DATA_DIR" \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown -h "$PUID:$PGID" {} +
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --inh-caps=-all "$0" "$@"
fi

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
    echo "The mapped host directory must be writable by that user. Remove --user" >&2
    echo "from the container's settings and it fixes the ownership itself, or chown" >&2
    echo "the directory to $(id -u):$(id -g). See docs/upgrading.md." >&2
    exit 1
fi

# Generate secret key if not provided
if [[ -z "${SECRET_KEY}" || "${SECRET_KEY}" = "change-me-in-production" ]]; then
    if [[ ! -f "$DATA_DIR/.secret_key" ]]; then
        # Owner-only from the moment it exists: this key signs every login token.
        (umask 077 && python -c "import secrets; print(secrets.token_hex(32))" > "$DATA_DIR/.secret_key")
        echo "Generated new secret key"
    fi
    chmod 600 "$DATA_DIR/.secret_key" 2>/dev/null || true
    SECRET_KEY="$(cat "$DATA_DIR/.secret_key")"
    export SECRET_KEY
fi

echo "Data directory: ${DATA_DIR}"
echo "Database: ${DATABASE_URL}"
echo "========================================="

# Run the application
exec "$@"
