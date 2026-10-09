# Rollback reference

## Production

Production runs a pinned version tag on Unraid (port 3014), not `:latest`.
It moves from 3.2.1 straight to 3.2.3; 3.2.2 was released and tested on
staging but never ran on production.

| | Next | Current | Before 3.x migrations |
| --- | --- | --- | --- |
| Version | 3.2.3 | 3.2.1 | 3.0.17 |
| Tag | `v3.2.3` | `v3.2.1` | `v3.0.17` |
| Commit | 9455079 | 5ca1dfc | 42d83e9 |
| Image | `ghcr.io/jongaydos/drone-unit-manager@sha256:7fb2fb7ca266a916779b301bbe2733fb3e966a36297371cfe4f85911af779aca` | `ghcr.io/jongaydos/drone-unit-manager@sha256:80e9b5d716563e012e1491cf2ff223eabbb93cc6f44b871e87beab2eaab68311` | `ghcr.io/jongaydos/drone-unit-manager@sha256:264f129219b17672bea90b6b3f9e04182dc9979fc6c7a3e198762d97c3055eb5` |
| Extra Parameters | `--restart unless-stopped` | `--restart unless-stopped` | `--restart unless-stopped --user 99:100` |

A version's image tag (`:3.2.3`) exists only after its `vX.Y.Z` git tag is
pushed and the release build has finished. Check it on ghcr.io before changing
production's Repository; an Apply to a missing tag removes the running container
and then fails to pull.

## Roll production back to 3.2.1

3.2.2 and 3.2.3 have no migrations, so this is the image alone: set the
Repository to `ghcr.io/jongaydos/drone-unit-manager:3.2.1` and Apply. The data
folder and Extra Parameters stay as they are.

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
