# Rollback reference

## Release images

Production runs a pinned version tag on Unraid (port 3014), not `:latest`.
Which version it runs is recorded in the owner's own notes, not here, so this
file changes only when a release is cut: each release PR adds its row below and
a "Roll production back" section for the release before it.
3.4.x and later read `TRUSTED_PROXIES`, set to the tunnel's address
(`172.17.0.1` on this host). 3.3.0 ignores that variable, so it can stay on a rollback.

| Version | Tag | Commit | Image | Extra Parameters |
| --- | --- | --- | --- | --- |
| 3.7.2 | `v3.7.2` | set when tagged | `ghcr.io/jongaydos/drone-unit-manager:3.7.2` (digest recorded after the tag build) | `--restart unless-stopped` |
| 3.7.1 | `v3.7.1` | set when tagged | `ghcr.io/jongaydos/drone-unit-manager:3.7.1` (digest recorded after the tag build) | `--restart unless-stopped` |
| 3.7.0 | `v3.7.0` | 0c776f4 | `ghcr.io/jongaydos/drone-unit-manager:3.7.0` (digest recorded after the tag build) | `--restart unless-stopped` |
| 3.6.0 | `v3.6.0` | 0e7dd41 | `ghcr.io/jongaydos/drone-unit-manager@sha256:3bdf543fdb7096c7f1bd602bad6d453fa64f02fa234cd0958e2d70b38fb728ed` | `--restart unless-stopped` |
| 3.5.0 | `v3.5.0` | 8e7b98b | `ghcr.io/jongaydos/drone-unit-manager@sha256:1bfe877604c0f45708e4c6abce8bcb73945ad162cd5fb6e7d1e59441d18ef0bb` | `--restart unless-stopped` |
| 3.4.2 | `v3.4.2` | 5b15043 | `ghcr.io/jongaydos/drone-unit-manager@sha256:36c52e7b1d20c14a9cfe76e24631fada57282d8968fcc5d44a9909aed20a712b` | `--restart unless-stopped` |
| 3.4.1 | `v3.4.1` | 8b3caaf | `ghcr.io/jongaydos/drone-unit-manager@sha256:283a2bc634643221f3b2d98035cd100f82009435f8decfb6862b2e47901b76c5` | `--restart unless-stopped` |
| 3.0.17 (before the 3.x migrations) | `v3.0.17` | 42d83e9 | `ghcr.io/jongaydos/drone-unit-manager@sha256:264f129219b17672bea90b6b3f9e04182dc9979fc6c7a3e198762d97c3055eb5` | `--restart unless-stopped --user 99:100` |

A version's image tag (`:3.3.0`) exists only after its `vX.Y.Z` git tag is
pushed and the release build has finished. Check it on ghcr.io before changing
production's Repository; an Apply to a missing tag removes the running container
and then fails to pull.

## Roll production back to 3.7.1 (from 3.7.2)

3.7.2 adds no migration. Set the Repository to
`ghcr.io/jongaydos/drone-unit-manager:3.7.1` and apply. 3.7.1's public
`/api/health` reports the version again, so check it says 3.7.1.

## Roll production back to 3.6.0 (from 3.7.1 or 3.7.0)

3.7.1 adds no migration, so rolling back from 3.7.1 is the same as from 3.7.0.
3.7.0 was tagged but never ran in production; production upgrades from 3.6.0
straight to 3.7.1. Every step below applies inside 3.7.1.

3.7.0 adds migration 0018. It drops the currency tables with their rows and
adds the rolling requirement tables, the per-user layouts and the aircraft
hourly operating cost. An older image cannot undo it, so run the downgrade
inside 3.7.1 (or 3.7.0) before switching back:

1. Take an in-app backup and copy the data folder. The downgrade deletes every
   rolling requirement lapse and excusal, every saved dashboard and analytics
   layout and every hourly operating cost.
2. With 3.7.1 still running, step the schema back one revision:

        docker exec -w /app <container> alembic downgrade 0017_flight_requirements

3. Check it reported `Running downgrade 0018_rolling_requirements -> 0017_flight_requirements`.
4. Remove the rolling requirements and rolling templates, which 3.6.0 cannot
   read (the requirements' pilots, models and purposes go with them):

        docker exec -w /app <container> python -c "from sqlalchemy import text; from app.database import engine; c = engine.connect(); n = c.execute(text(\"DELETE FROM flight_requirements WHERE period_type = 'rolling'\")).rowcount; t = c.execute(text(\"DELETE FROM flight_requirement_templates WHERE json_extract(settings, '$.period_type') = 'rolling'\")).rowcount; c.commit(); print(n, 'requirements and', t, 'templates removed')"

5. Set the Repository to `ghcr.io/jongaydos/drone-unit-manager:3.6.0` and Apply.
   The data folder and Extra Parameters stay as they are.

The downgrade recreates the currency tables empty: currency rules dropped by
the upgrade do not come back. If you need them, restore the backup made before
the upgrade to 3.7.1 (anything recorded since is lost), or recreate the rules
by hand in 3.6.0. Distances, landing locations and landing times filled in by
the 3.7 upgrade stay. To return to 3.7.1, run it again; it applies the migration on start.

## Roll production back to 3.5.0 (from 3.6.0)

Step back to 3.6.0 first (above).

3.6.0 adds two migrations. 0016 moves each currency rule's vehicle model into a
list (`currency_rule_models`); 0017 adds the Flight Requirements tables. An
older image cannot undo them, so run the downgrade inside 3.6.0 before
switching back:

1. Take an in-app backup and copy the data folder. The downgrade deletes every
   flight requirement, its saved results and templates, and a currency rule
   with several models keeps only the first one (alphabetically).
2. With 3.6.0 still running, step the schema back two revisions:

        docker exec -w /app <container> alembic downgrade 0015_drop_geofences

3. Check it reported `Running downgrade 0017_flight_requirements -> 0016_currency_rule_models`
   and `Running downgrade 0016_currency_rule_models -> 0015_drop_geofences`.
4. Set the Repository to `ghcr.io/jongaydos/drone-unit-manager:3.5.0` and Apply.
   The data folder and Extra Parameters stay as they are.

On 3.5.0, restore only a backup made before the upgrade to 3.6.0: a later
backup brings currency rules back with their old single model. To return to
3.6.0, run it again; it applies both migrations on start.

## Roll production back to 3.4.2 (from 3.5.0)

Step back to 3.5.0 first (above).

3.5.0 adds two migrations. 0014 rebuilds every table with AUTOINCREMENT ids
(rows, ids, indexes and foreign keys are copied as they are). 0015 drops the
geofences table; its downgrade recreates the table empty, so any geofence rows
are gone either way. An older image cannot undo them, so run the downgrade
inside 3.5.0 before switching back:

1. Copy the data folder first. A backup exported from 3.5.0 holds password
   hashes, API tokens and integration secrets, so keep it like a password.
2. With 3.5.0 still running, step the schema back two revisions:

        docker exec -w /app <container> alembic downgrade 0013_clean_flight_battery_serials

3. Check it reported `Running downgrade 0015_drop_geofences -> 0014_autoincrement_ids`
   and `Running downgrade 0014_autoincrement_ids -> 0013_clean_flight_battery_serials`.
4. Set the Repository to `ghcr.io/jongaydos/drone-unit-manager:3.4.2` and Apply.
   The data folder and Extra Parameters stay as they are.

After the downgrade, ids can be reused again (the 3.4.2 behaviour). To return to
3.5.0 later, run it again; it applies both migrations on start.

## Roll production back to 3.4.1

Step back to 3.4.2 first (above).

3.4.2 has no migration. Set the Repository to
`ghcr.io/jongaydos/drone-unit-manager:3.4.1` and Apply.

## Roll production back to 3.4.0

The 3.4.0 image is
`ghcr.io/jongaydos/drone-unit-manager@sha256:215ed55ac7f3925bd6293cb91b250ae97b30970062107deb4ac978ec5eb2f1a0`.

3.4.1 adds migration 0013, which only removes a leading dash from stored flight
battery serials. Its downgrade changes nothing, and 3.4.0 reads the cleaned
values as they are, so no data step is needed:

1. Optionally step the schema back so the migration history matches:

        docker exec -w /app <container> alembic downgrade 0012_audit_identity

2. Set the Repository to `ghcr.io/jongaydos/drone-unit-manager:3.4.0` and Apply.

## Roll production back to 3.3.0

Step back to 3.4.0 first, then use the migration 0012 steps under "Roll back a release with migration 0012" below.

## Roll production back to 3.2.3

Step back to 3.3.0 first (its image is
`ghcr.io/jongaydos/drone-unit-manager@sha256:d65a9f731f24ec1b78ce8e75558db151a471d194f0da279c054fc71064dda1ec`), then use the migration 0011 steps under "Roll back a
release with migration 0011" below. The 3.2.3 image is
`ghcr.io/jongaydos/drone-unit-manager@sha256:7fb2fb7ca266a916779b301bbe2733fb3e966a36297371cfe4f85911af779aca`.

## Roll production back to 3.0.17

The 3.1.x migrations (0006 to 0010) change the database and cannot be undone by
an older image, so a rollback needs the data folder copied before the upgrade
(`/mnt/user/appdata/drone-unit-manager.pre-3.2.0`), not just the old image.

1. Stop the container.
2. Swap the data folders:

        mv /mnt/user/appdata/drone-unit-manager /mnt/user/appdata/drone-unit-manager.failed-3.2.0
        mv /mnt/user/appdata/drone-unit-manager.pre-3.2.0 /mnt/user/appdata/drone-unit-manager

3. Set the Repository to `ghcr.io/jongaydos/drone-unit-manager:3.0.17`.
4. Put `--user 99:100` back in Extra Parameters. 3.0.17 runs as uid 1000 and
   cannot write the 99:100-owned folder without it.
5. Start the container and check `/api/health` reports 3.0.17.

Anything recorded in production after the upgrade is in the `failed-3.2.0`
folder, not in the restored copy.

## Roll back a release with migration 0011 (role permissions)

3.3.0 is the first release with this migration, so its rollback target is 3.2.3.

Migration 0011 creates `role_permissions` and adds `documents.uploaded_by_id`.
An older image cannot undo it, so run the downgrade inside the new image
before switching back to the older one:

1. In the app, take a backup first (Settings, General, Backup & Restore,
   Export Backup), and copy the data folder as well.
2. With the new image still running, step the schema back one revision:

        docker exec -w /app <container> alembic downgrade 0010_local_dates_for_spreadsheet_imports

3. Check it reported `Running downgrade 0011_role_permissions -> 0010_local_dates_for_spreadsheet_imports`.
4. Set the Repository to the older tag (`ghcr.io/jongaydos/drone-unit-manager:3.2.3`) and Apply. The data folder and Extra
   Parameters stay as they are.

The downgrade drops the `role_permissions` table and the
`documents.uploaded_by_id` column. Every admin change to role permissions and
the recorded uploader of each document are lost, and the older release goes back
to its fixed role rules. To return to the new release later, run it again; it
applies the migration on start and the permission grid starts at the defaults.

## Roll back a release with migration 0012 (audit log identity)

Migration 0012 adds `audit_logs.user_username` and `audit_logs.imported`. An
older image cannot undo it, so run the downgrade inside the new image before
switching back. If the release you are leaving also carries migration 0011,
step back past both by following the 0011 section afterwards.

1. In the app, take a backup first (Settings, General, Backup & Restore,
   Export Backup), and copy the data folder as well.
2. With the new image still running, step the schema back one revision:

        docker exec -w /app <container> alembic downgrade 0011_role_permissions

3. Check it reported `Running downgrade 0012_audit_identity -> 0011_role_permissions`.
4. Set the Repository to the previous tag and Apply. The data folder and Extra
   Parameters stay as they are.

The downgrade drops the two columns and the index on entry dates. Audit entries stay, but the recorded
login name of who made each change and the marker for entries that came from a
restored backup are lost. To return to the new release later, run it again; it
applies the migration on start, and older entries have no login name.

## Roll the code back

    git revert <commit>
    git push

CI rebuilds and republishes `:main`. Production moves only when its tag is changed.

## Earlier baseline

Known-good state before the SonarCloud cleanup: tag `known-good-2026-09-05`,
commit 511d30a, image
`ghcr.io/jongaydos/drone-unit-manager@sha256:a53b0c03f826a7a1f048a0295c0497318abc0ef89e542ed821053cde7c62ff0a`.
