# Rollback reference

## Production

Production runs a pinned version tag on Unraid (port 3014), not `:latest`.

| | Current | Previous |
| --- | --- | --- |
| Version | 3.2.0 | 3.0.17 |
| Tag | `v3.2.0` | `v3.0.17` |
| Commit | 0aa5b7f | 42d83e9 |
| Image | `ghcr.io/jongaydos/drone-unit-manager@sha256:f47c2b58a3a1609912a0a2e7dbacd59f634956a91b73e4f7a0a07ed6ca628a53` | `ghcr.io/jongaydos/drone-unit-manager@sha256:264f129219b17672bea90b6b3f9e04182dc9979fc6c7a3e198762d97c3055eb5` |
| Extra Parameters | `--restart unless-stopped` | `--restart unless-stopped --user 99:100` |

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

## Roll the code back

    git revert <commit>
    git push

CI rebuilds and republishes `:main`. Production moves only when its tag is changed.

## Earlier baseline

Known-good state before the SonarCloud cleanup: tag `known-good-2026-09-05`,
commit 511d30a, image
`ghcr.io/jongaydos/drone-unit-manager@sha256:a53b0c03f826a7a1f048a0295c0497318abc0ef89e542ed821053cde7c62ff0a`.
