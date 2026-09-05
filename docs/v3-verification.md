# v3 verification checklist

Everything merged since 2.2.0, and what to check before production moves.

Run all of it against **staging on port 3015**. Production on 3014 stays on
`:2.2.0` throughout: that tag can only be republished by pushing a `v*` git tag,
and no merge to `main` does that. Its digest is `sha256:93fe2561…` and has not
moved.

---

## 0. Before anything else: staging has to start

The container no longer runs as root, and this is the one change that can stop
it starting. Do this first.

- [ ] From the Unraid terminal:
      `chown -R 99:100 /mnt/user/appdata/drone-unit-manager-staging`
- [ ] Edit the staging container, **Extra Parameters**:
      `--restart unless-stopped --user 99:100`
- [ ] Force update / pull `:main` and start it
- [ ] `docker exec <staging-container> id` prints `uid=99`
- [ ] `curl http://192.168.0.100:3015/api/health` returns
      **`"version":"3.0.0-rc1"`** and `"database":"connected"`

The version string is how you tell the two apart. Production still says
`2.2.0`. If staging also says `2.2.0`, it did not pull the new image.

If the container exits immediately, read its log. The entrypoint checks the
data directory before anything else and says which uid it is running as. That
message means the `chown` above was missed or did not take.

---

## 1. Flights: bulk edits (the 2026-09-03 incident)

A purpose picked from the toolbar dropdown used to apply instantly. On
2026-09-03 that replaced the purpose on 97 flights in one click, with nothing
shown before or after.

- [ ] Flights, tick several rows, pick a purpose from **Set purpose…**
- [ ] A dialog appears naming the new purpose, how many flights are selected,
      how many will actually change, and which purposes are being replaced
      (e.g. `4 will change, replacing: Map Scan (3), Training (1)`)
- [ ] **Cancel** sends nothing. The rows are unchanged.
- [ ] Confirm, and the change applies as before
- [ ] Same dialog for **Reassign pilot…** and **Mark reviewed**
- [ ] Select rows that already have the target purpose: it says
      *"All N selected flights already have the purpose … Nothing will change."*
- [ ] Audit Log now shows the bulk edit with the values it replaced and the
      flight ids it touched, not just "Updated N flights"

## 2. Dashboard: countdowns moved by a day

**Expect the numbers to change.** The dashboard had its own date helper that
read `2026-09-10` as UTC midnight, which is the evening of the 9th here. Every
countdown was one day short.

- [ ] Dashboard and Compliance now agree on the same pilot's days-to-expiry.
      They used to differ by one; Compliance was the correct one.
- [ ] Maintenance due today reads `0d`, not `1d -`
- [ ] Something 30 days out reads `30d` and is blue, not amber
- [ ] Badge colours still read: red past due, amber close, blue comfortable
- [ ] Weather advisory still colours GO green, NO-GO red, anything else amber

## 3. Flight log import

Three parser defects were fixed. If you have any of these files, import one.

- [ ] A **DJI** `.txt` whose header uses `CUSTOM.date` (no `DateTime(utc)`)
      now imports with telemetry. It previously imported zero points.
- [ ] An **Airdata** CSV now records speed and a max speed. That column was
      never being read.
- [ ] A log with a truncated final row imports rather than failing outright
- [ ] BRINC CSV import still behaves as it did: unmatched drones listed,
      created pilots named, zero-duration rows reported
- [ ] Importing the same file twice still reports the second as a duplicate

## 4. Documents

- [ ] The folder tree looks and behaves exactly as before
- [ ] Expand and collapse a folder with sub-folders
- [ ] Select a folder; its documents load
- [ ] Rename and delete controls still appear on hover for a supervisor
- [ ] Upload a document (this also proves the container can write)

## 5. Settings: drone locations

- [ ] Settings, Drone Locations: add a place, type a name
- [ ] Remove a row above one you are typing in — you stay in the field you
      were editing, and the other rows keep their own names
- [ ] Save, reload the page, the list is as you left it
- [ ] The dashboard location dropdown shows the saved places

## 6. Backups (fixed yesterday, worth re-proving here)

- [ ] Settings, run a manual backup export. It completes rather than timing
      out at 30 seconds.
- [ ] The download opens and the zip is readable
- [ ] The 3am automatic backup still lands (check after a night, or check
      the backups folder for the most recent one)

## 7. Everything else that was touched

Quick regression pass, all of these had code changed under them:

- [ ] Modals: open one, Tab to the last control, Tab again — focus wraps back
      into the dialog rather than escaping behind it
- [ ] Media: open the upload dialog, pick a pilot chip, click it again to
      un-pick it
- [ ] Equipment checkouts: check something out, then check it in — the person
      who took it out is pre-selected as returning it
- [ ] Compliance: the Currency Compliance tile shows a percentage, or `—`
      with *no rules* underneath when no currency rule is configured
- [ ] Operating Authority: the list, the empty state, and the loading state
- [ ] Maintenance: add a record and edit one; the button says *Add* then
      *Update*
- [ ] Integrations: run a Skydio sync; the status block and its next-sync
      line still read correctly
- [ ] User Manual: bulleted lines still render their bold term
- [ ] Calendar, certifications, reports, exports: nothing changed here, but
      they share components that did

---

## 8. When staging passes

Tell me and I will:

1. Bump `APP_VERSION` from `3.0.0-rc1` to `3.0.0`
2. Tag `v3.0.0`, which is what publishes `:3.0.0` and moves `:latest`
3. Give you the production steps, which are the same two from section 0 —
   `chown -R 99:100` on the production appdata and `--user 99:100` in Extra
   Parameters — plus changing the repository to `:3.0.0`

Take a fresh appdata backup before that, as usual. Rolling back is changing the
repository field back to `ghcr.io/jongaydos/drone-unit-manager:2.2.0` and
restarting; that image is untouched and still there.

---

## Known and deliberate

- **Sonar shows ~60 open issues.** 36 are cognitive-complexity findings in
  `reports.py`, `export.py`, `skydio.py` and others, sitting at 29% to 69%
  coverage. Refactoring those without tests first is how compliance reporting
  breaks quietly, so they are left alone. Writing that coverage is its own
  piece of work, not a pre-release rush.
- **Three findings are wrong** and worth marking *won't fix* in the SonarCloud
  UI: `IntegrationsPage.jsx:355` (the suggested `<=` would let `NaN` through),
  `export.py` (the flagged `http://` is the GPX XML namespace, not a request),
  and `Card.jsx` (a generic heading whose content arrives as children).
- **Six are in `migrations/0001_baseline.py`**, which has already run on every
  install. Historical record; left alone.
- **`role="dialog"` on the modal** could be a native `<dialog>`. That is a
  rewrite of the most-used component in the app, and the hand-rolled version
  is complete and tested. After v3, not before it.
