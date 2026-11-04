# Upgrading

## Release checks: image scan and database step

The release build scans the image and stops before publishing if it finds a
fixable HIGH or CRITICAL package issue. If a build is blocked, read the scan
output in the run log. Either update the named package (rebuild, or bump the
base image or dependency) or have the owner decide whether to accept it, and
record that decision before re-running. Issues with no fix available do not
block.

This release adds migration 0012 (login name and imported marker on audit
entries). It runs on start. To go back, see `ROLLBACK.md`.

Behind a reverse proxy or tunnel, set `TRUSTED_PROXIES` before upgrading (see
"Reverse Proxy" in the README).

## Restoring a backup: held items and audit entries

A restore replaces the database with the backup. If that would remove or change
a photo or document under legal hold, the restore is refused with a list of the
held items and nothing changes. To go ahead, send the form field
`confirm_holds` with the exact text `RESTORE HELD ITEMS` to
`POST /api/backup/import`. On a live install this is an API step with an admin
token: the setup screen restores only into a fresh install, which has no held
items. Each held item the restore removed or changed gets its own audit entry.
A held item the backup carries unchanged needs no confirmation.

The audit entries in a backup are added to this install's own, marked as
imported, and one summary entry records the backup date, how many were added,
and what was restored, including a telemetry or file step that failed. Backups from before the audit log recorded usernames restore the same
way.

## 3.1.10: the container fixes its data folder's ownership

From 3.1.10 the container starts as root only long enough to give the data
directory to the app's user, then drops to that user before the app starts. The
app itself still never runs as root. A data folder that is deleted and recreated,
or copied in as root, no longer stops the container: there is no manual `chown`.

The user is chosen with two variables, `PUID` and `PGID`, defaulting to `99` and
`100` (Unraid's `nobody:users`). Only files not already owned by that user are
changed, so a start does not rewrite a large data folder.

To use it, **remove `--user 99:100` from Extra Parameters** (the templates in the
repository no longer carry it). Leaving `--user` in place keeps the behaviour
described below: the container runs as that user from the start and the folder
must already be writable by it. `PUID=0` keeps root deliberately.

## To v3: the container no longer runs as root

Every version up to and including 2.2.0 ran the application as `root` inside the
container. From v3 it runs as an ordinary user, `app` (uid 1000, gid 1000).

Nothing outside `/app/data` is written at runtime, so this is the only thing
that changes: **the mapped host directory has to be writable by the user the
container runs as.** On an existing install that directory is owned by `root`,
because the container that created it was root, so it needs one of the two steps
below before the container will start.

The entrypoint checks this first and stops with an explicit message rather than
failing somewhere further in, so a container that exits immediately after an
upgrade is almost certainly this. Check the log.

### Unraid

`appdata` is conventionally owned by `nobody:users`, uid 99 gid 100. Add this to
the container's **Extra Parameters** (both templates in the repository already
carry it):

```
--user 99:100
```

Then hand the existing directory to that user, once, from the Unraid terminal:

```bash
chown -R 99:100 /mnt/user/appdata/drone-unit-manager
```

`--user` overrides the image's own user, so the uid the image was built with
stops mattering.

### Docker Compose or plain Docker

Either give the directory to uid 1000:

```bash
chown -R 1000:1000 /path/to/your/data
```

or run as whichever user already owns it:

```yaml
services:
  app:
    user: "1000:1000"   # or whatever `stat -c '%u:%g' /path/to/your/data` says
```

### Staying on root

Adding `--user 0:0` keeps the old behaviour. It is a valid escape hatch during a
migration, but it gives up what the change is for: a container escape from a
root process is an escape as root on the host.

## Checking it worked

```bash
docker exec <container> id
```

should print the uid the data directory is owned by, and

```bash
curl -s http://<host>:<port>/api/health
```

should return `{"status":"ok",...}` with a `database` of `connected`. A container
that starts but reports the database as unavailable is usually a data directory
the process can read but cannot write.
