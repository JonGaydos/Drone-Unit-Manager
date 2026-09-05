# Upgrading

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
