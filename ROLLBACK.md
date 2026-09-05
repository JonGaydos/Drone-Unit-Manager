# Rollback reference

Known-good baseline before the SonarCloud cleanup.

| | |
| --- | --- |
| Tag | `known-good-2026-09-05` |
| Commit | 511d30a |
| Image | `ghcr.io/jongaydos/drone-unit-manager@sha256:a53b0c03f826a7a1f048a0295c0497318abc0ef89e542ed821053cde7c62ff0a` |

## Roll back the running container

Pin the digest in `docker-compose.yml`, then bring it up:

    image: ghcr.io/jongaydos/drone-unit-manager@sha256:a53b0c03f826a7a1f048a0295c0497318abc0ef89e542ed821053cde7c62ff0a

    docker compose up -d

Unpin (back to `:main`) once the cause is fixed.

## Roll back the code

    git revert -m 1 <squash merge sha>
    git push

CI rebuilds and republishes `:main` automatically.

## Stage log

Filled in as each stage merges.

| Stage | Scope | Merge SHA | Image digest |
| --- | --- | --- | --- |
| baseline | clean repo | 511d30a | sha256:a53b0c03 |
| timeout fix | backup/report/import request timeouts | 68e51a4 | pending build |
