#!/bin/bash
# Drone Unit Manager — host-side consistent backup for Unraid.
#
# Runs a WAL-safe SQLite snapshot of BOTH databases (via the container's own
# Python sqlite3 .backup, which is consistent even while the app is running) and
# a tar of the uploads directory, then rotates to the last $KEEP of each.
#
# Setup (Unraid):
#   1. Install the "User Scripts" plugin (Community Apps).
#   2. Add a new script, paste this in, and set a schedule (e.g. daily 3:00 AM).
#   3. Adjust CONTAINER, APPDATA, and KEEP below to match your install.
#   4. (Recommended) Also enable the "Appdata Backup" plugin so /backups gets
#      carried offsite with the rest of appdata.
#
# This is independent of the app's own in-app daily backup — running both gives
# you two separate copies (host snapshot + app-generated redacted ZIP).

set -u

CONTAINER="Drone-Unit-Manager"                       # <-- your container name
APPDATA="/mnt/user/appdata/drone-unit-manager"       # <-- host path of /app/data
KEEP=7                                                # how many of each to retain

DEST="$APPDATA/backups/host"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"

# Consistent SQLite snapshots, written inside the container to /app/data/backups/host
docker exec "$CONTAINER" python -c "
import sqlite3
for name in ('drone_unit_manager', 'telemetry'):
    src = sqlite3.connect(f'/app/data/{name}.db')
    dst = sqlite3.connect(f'/app/data/backups/host/{name}-$STAMP.db')
    with dst:
        src.backup(dst)
    dst.close(); src.close()
print('db snapshot ok')
"

# Uploads (static files) — tar from the host side
if [ -d "$APPDATA/uploads" ]; then
  tar -czf "$DEST/uploads-$STAMP.tar.gz" -C "$APPDATA" uploads
fi

# Rotate: keep the newest $KEEP of each artifact type
for pat in "drone_unit_manager-*.db" "telemetry-*.db" "uploads-*.tar.gz"; do
  # shellcheck disable=SC2012
  ls -1t "$DEST"/$pat 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old"
  done
done

echo "DUM host backup $STAMP complete -> $DEST"

# ---------------------------------------------------------------------------
# RESTORE (host snapshot):
#   Stop the container, then copy the chosen *.db files back over
#   $APPDATA/drone_unit_manager.db and $APPDATA/telemetry.db, and extract
#   uploads-*.tar.gz into $APPDATA/. Start the container; Alembic upgrades on boot.
# (For a portable, secret-redacted restore use the app's in-app backup ZIP +
#  Settings -> Backup & Restore instead.)
