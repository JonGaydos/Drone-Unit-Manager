# Rollback reference

## Production

Production runs a pinned version tag on Unraid (port 3014), not `:latest`.
It moved from 3.2.3 to 3.3.0 (running on production, confirmed by the owner
2026-11-03). 3.3.0 has migration 0011, so rolling back needs the steps below, not just
the older image.

The next release, 3.4.0, has migration 0012, so its rollback target is 3.3.0.
Use the migration 0012 steps below.

| | Current | Rollback target | Before 3.x migrations |
| --- | --- | --- | --- |
| Version | 3.3.0 | 3.2.3 | 3.0.17 |
| Tag | `v3.3.0` | `v3.2.3` | `v3.0.17` |
| Commit | 48013c0 | 9455079 | 42d83e9 |
| Image | `ghcr.io/jongaydos/drone-unit-manager@sha256:d65a9f731f24ec1b78ce8e75558db151a471d194f0da279c054fc71064dda1ec` | `ghcr.io/jongaydos/drone-unit-manager@sha256:7fb2fb7ca266a916779b301bbe2733fb3e966a36297371cfe4f85911af779aca` | `ghcr.io/jongaydos/drone-unit-manager@sha256:264f129219b17672bea90b6b3f9e04182dc9979fc6c7a3e198762d97c3055eb5` |
| Extra Parameters | `--restart unless-stopped` | `--restart unless-stopped` | `--restart unless-stopped --user 99:100` |

A version's image tag (`:3.3.0`) exists only after its `vX.Y.Z` git tag is
pushed and the release build has finished. Check it on ghcr.io before changing
production's Repository; an Apply to a missing tag removes the running container
and then fails to pull.

## Roll production back to 3.2.3

Use the migration 0011 steps under "Roll back a release with migration 0011" below.

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

The downgrade drops the two columns. Audit entries stay, but the recorded
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
