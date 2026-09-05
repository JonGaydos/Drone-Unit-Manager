# Staging instance

A second container running the same app against a copy of real data, so merged
work can be exercised before a release moves production.

## Release channels

| Tag | Moves when | Who tracks it |
| --- | --- | --- |
| `:latest`, `:X.Y.Z` | a `v*` release tag is pushed | production |
| `:v2` | every merge to `v2` | staging |
| `:<short-sha>` | every build | anyone pinning to an exact commit |

`:latest` deliberately does not follow `main`. It used to, which meant any merge
reached a production container on its next pull with no step in between where a
person decided to ship.

## Setting it up

Add the container from `unraid-template-staging.xml`. It differs from production
in exactly three places, and all three must differ or the two instances will
collide:

- image `:v2` rather than a release tag
- host port `3015` rather than `3014`
- appdata `/mnt/user/appdata/drone-unit-manager-staging`

## Seeding it from production

Stop nothing; the copy is read-only against production's directory.

    rsync -a /mnt/user/appdata/drone-unit-manager/ \
             /mnt/user/appdata/drone-unit-manager-staging/

That is a full copy including `telemetry.db`, so budget for the size: telemetry
is the overwhelming majority of it. To leave it out, add
`--exclude 'telemetry.db*'`; the app recreates an empty one on start and
everything except flight tracks still works.

## Neutering the copy, before first start

**Do this before you start the container.**

A copy of production's appdata carries production's settings, which include the
SMTP credentials and the Skydio API token. The scheduler starts four jobs on
boot: the Skydio sync, the telemetry sync, the nightly backup, and the email
digest. Left alone, a staging instance will sync the real Skydio account and
send the digest to real recipients.

    docker run --rm \
      -v /mnt/user/appdata/drone-unit-manager-staging:/app/data \
      --entrypoint python \
      ghcr.io/jongaydos/drone-unit-manager:v2 \
      -c "import sqlite3; c = sqlite3.connect('/app/data/drone_unit_manager.db'); c.execute(\"DELETE FROM settings WHERE key IN ('smtp_host','smtp_username','smtp_password','skydio_api_token','skydio_token_id')\"); c.execute(\"UPDATE settings SET value='false' WHERE key='backup_enabled'\"); c.execute(\"UPDATE settings SET value='0' WHERE key IN ('sync_interval','telemetry_sync_interval')\"); c.commit(); print('cleared', c.total_changes, 'rows')"

It removes the SMTP and Skydio credentials, disables the nightly backup, and
sets both sync intervals to zero. Re-run it after any later reseed from
production, because a reseed brings the settings back.

## Cutting a release

When staging has proved a change, tag the commit and production picks it up on
its next pull:

    git tag -a v2.3.0 -m "Release 2.3.0"
    git push origin v2.3.0

That builds and publishes `:2.3.0` and `:latest` from that exact commit.

## Rolling back

Every build is tagged with its short commit SHA, so production can be pointed at
any previous build by changing the Repository field to
`ghcr.io/jongaydos/drone-unit-manager:<sha>` and applying.
