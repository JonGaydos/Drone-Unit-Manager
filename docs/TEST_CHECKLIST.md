# Drone Unit Manager v2.2.0 — Full Test Checklist (Fresh Install)

Test from a completely clean database. Check each item as you go.

---

## 1. First-Run Setup
- [ ] App loads at http://192.168.0.100:3014 — shows setup wizard (not login)
- [ ] Create admin account (username, password, display name, org name, email)
- [ ] Password policy enforced (12+ chars, uppercase, number)
- [ ] Auto-logged in after setup — redirected to dashboard
- [ ] Setup page blocked if visited again (already has users)
- [ ] Admin user auto-created as a pilot (linked pilot record)

## 2. Dashboard
- [ ] Dashboard loads with empty state (no flights, no alerts)
- [ ] Stats cards show zeros (flights, hours, vehicles, pilots)
- [ ] No errors in browser console
- [ ] Cert Expirations sidebar excludes inactive pilots

## 3. Settings — General
- [ ] Organization name displays correctly
- [ ] Theme switcher works (Dark, Light, Glass, Grafana)
- [ ] Settings save without errors
- [ ] Organization logo upload works
- [ ] Weather thresholds configurable (defaults load, can save custom values)
- [ ] Weather thresholds "Reset to Defaults" button works
- [ ] Sidebar config shows "Airspace" and "Activity Reports"

## 4. Settings — Users
- [ ] Create a second user (supervisor role)
- [ ] Create a third user (pilot role)
- [ ] User list shows all 3 users
- [ ] Edit user role/display name
- [ ] Reset user password (admin action)
- [ ] Disable/enable a user account

## 5. Settings — Integrations (Skydio)
- [ ] Enter Skydio API token and Token ID
- [ ] Test Connection — shows success with user info
- [ ] Sync Now — imports flights, vehicles, batteries, etc.
- [ ] Sync results display (flights imported, vehicles, equipment)

## 6. Pilots
- [ ] Add a pilot manually (name, badge, email, phone)
- [ ] Pilot appears in list
- [ ] Click pilot name — detail page loads
- [ ] Edit pilot details
- [ ] Link pilot to a user account
- [ ] Delete a pilot

## 7. Fleet — Vehicles
- [ ] Vehicles tab shows synced vehicles (or add manually)
- [ ] Click vehicle — detail page loads
- [ ] Vehicle stats display (hours, flights, registrations)
- [ ] Edit vehicle details (FAA Registration field removed — use detail page instead)
- [ ] FAA Registration section on detail page — add registration with auto +3 year expiry
- [ ] "Next Due" column shows days remaining from VehicleRegistration records
- [ ] FAA Reg column shows registration number from VehicleRegistration records

## 8. Fleet — Batteries
- [ ] Batteries tab shows synced batteries (or add manually)
- [ ] Click battery — detail page loads
- [ ] Add battery health reading
- [ ] Health trending chart displays
- [ ] Edit battery details

## 9. Fleet — Controllers, Sensors, Attachments, Docks
- [ ] Each tab displays items
- [ ] Can add new items manually
- [ ] Can edit/delete items
- [ ] Click item — detail page loads
- [ ] Each fleet item shows: flight history, maintenance, relevant stats

## 10. Fleet — Equipment Merge
- [ ] Select two duplicate items
- [ ] Merge completes without errors
- [ ] Merged item retains data from both

## 11. Flights
- [ ] Flight list shows synced flights
- [ ] Click a flight — detail page loads
- [ ] Flight map displays GPS path (if telemetry exists)
- [ ] Altitude/speed/battery charts render
- [ ] Edit flight details (purpose, case number, notes)
- [ ] Review status toggle works (needs_review -> reviewed)
- [ ] Cross-reference links work (pilot, vehicle, battery names are clickable)
- [ ] "No Purpose" filter option shows flights missing purpose codes

## 12. Flight Import — CSV
- [ ] Export flights to CSV
- [ ] Re-import the CSV — deduplication works (no double entries)

## 13. Flight Import — Excel / Airdata
- [ ] Import Excel spreadsheet with auto-detect — toast shows correct count (not 0)
- [ ] Import Airdata JSON file
- [ ] Import Airdata CSV file
- [ ] Import Airdata ZIP (multiple files)
- [ ] Multi-file select works
- [ ] Imported flights appear with correct data

## 14. Flight Plans
- [ ] Create a new flight plan
- [ ] Submit for approval
- [ ] Login as supervisor — approve/deny the plan
- [ ] Status updates correctly

## 15. Pre-Flight Checklists
- [ ] Create a checklist template
- [ ] Add checklist items
- [ ] Complete a checklist (check all items)
- [ ] View completed checklist history

## 16. Certifications
- [ ] Add a certification type (set renewal_period_months for expiring certs)
- [ ] Assign certification to a pilot
- [ ] Set expiration date
- [ ] Expiring cert shows warning
- [ ] Certification matrix displays correctly (renewed certs hidden)
- [ ] Renew a certification — click Renew button, enter new dates
- [ ] Renewal auto-calculates expiry from cert type renewal_period_months
- [ ] Renewal history shows in Edit modal
- [ ] Old cert status changes to "renewed" (indigo badge)

## 17. Maintenance
- [ ] Add a maintenance record
- [ ] Record appears in history
- [ ] Create a maintenance schedule (recurring)
- [ ] Overdue maintenance shows alert

## 18. Mission Logs
- [ ] Create a mission log entry
- [ ] Add pilots to the mission
- [ ] Link flights to the mission
- [ ] Mission list displays correctly

## 19. Training Logs
- [ ] Create a training log entry
- [ ] Add pilots/trainees
- [ ] Set outcome (pass/fail/in-progress)
- [ ] Training list displays correctly

## 20. Incidents
- [ ] Report a new incident
- [ ] Set severity and category
- [ ] Add resolution
- [ ] Incident list displays correctly

## 21. Weather Briefing
- [ ] Enter GPS coordinates (or click map)
- [ ] Weather loads — METAR, TAF, local weather
- [ ] GO/CAUTION/NO-GO advisory displays
- [ ] Forecast shows 12-hour outlook
- [ ] Custom thresholds apply correctly

## 22. ADS-B Airspace
- [ ] Map loads with location
- [ ] Nearby aircraft display (if any in range)
- [ ] Click aircraft — shows details
- [ ] Radius slider works
- [ ] Auto-refresh runs without error toasts

## 23. Analytics
- [ ] Charts load (flights by pilot, purpose, year)
- [ ] Cross-filtering works (click a bar to filter)
- [ ] Flight locations map displays
- [ ] Pilot leaderboard table renders with row numbers

## 24. Compliance Dashboard
- [ ] Compliance score calculates
- [ ] Expired items flagged (excludes renewed certs)
- [ ] Expiring items exclude inactive pilots
- [ ] Attention items listed (no [object Object] or key warnings)

## 25. Reports
- [ ] Generate Flight Summary report
- [ ] Generate Pilot Hours report
- [ ] Generate Equipment Utilization report
- [ ] PDF download works
- [ ] Organization logo appears on PDF (not squished)
- [ ] CSV export works on each page

## 26. Documents
- [ ] Upload a document (PDF, image, etc.)
- [ ] Assign to pilot/vehicle/certification
- [ ] Document appears in folder view
- [ ] Download/view document
- [ ] File type restriction enforced (no .exe, etc.)

## 27. Photo Gallery
- [ ] Upload a photo — file accepted
- [ ] Thumbnail displays in grid (not broken image)
- [ ] Click photo — lightbox shows full image (not just filename text)
- [ ] Associate photo with pilots
- [ ] Date grouping displays
- [ ] Edit photo metadata
- [ ] Delete photo

## 28. Email Digest
- [ ] Configure SMTP settings (Integrations page — server, port, credentials)
- [ ] Send test digest — email received (or appropriate error if no email set)
- [ ] Preview digest — shows pending approvals, needs review, incidents
- [ ] Notification preferences — categories toggle on/off

## 29. Audit Log
- [ ] Actions logged (login, create, edit, delete)
- [ ] Filter by action type
- [ ] Filter by user
- [ ] Timestamps correct
- [ ] Entries show display name and login name, and the full old and new values
- [ ] A bulk change or import writes one summary entry naming who started it
- [ ] Email and phone values are hidden in the log and the CSV export
- [ ] Export CSV has Username and Imported columns and covers more than 5,000 entries

## 30. Cross-Reference Links
- [ ] Pilot names link to pilot detail (everywhere they appear)
- [ ] Vehicle names link to vehicle detail
- [ ] Battery serials link to battery detail
- [ ] Sensor/attachment names link to fleet page
- [ ] Flight IDs link to flight detail
- [ ] Purpose codes link to filtered flight list

## 31. Modals (Click-to-Dismiss)
- [ ] Click outside any modal — it closes
- [ ] Press Escape — modal closes
- [ ] Modal content is scrollable if tall
- [ ] Close X button works

## 32. Responsive / Mobile
- [ ] Sidebar collapses on mobile
- [ ] Pages are usable on tablet width
- [ ] Tables scroll horizontally on small screens

## 33. Security
- [ ] Logout works — redirected to login
- [ ] Can't access pages without login (API returns 401)
- [ ] Pilot role can't access admin functions
- [ ] Rate limiting: 5 wrong passwords = lockout message
- [ ] Login after lockout period works

## 34. Validation Errors
- [ ] Submit maintenance form with empty description — shows readable error (not [object Object])
- [ ] Submit any form with missing required field — error message is human-readable

## 35. Backup & Restore
- [ ] Settings > General > "Backup & Restore" section visible (admin only)
- [ ] Export Backup downloads a ZIP file
- [ ] Export with telemetry checkbox — ZIP includes telemetry.json
- [ ] Fresh install Setup page shows "Restore from a backup instead?" option
- [ ] Upload backup ZIP — restore completes with stats
- [ ] After restore, login with original credentials works
- [ ] All data present after restore (flights, pilots, certs, photos, documents)
- [ ] Restoring a backup that would remove or change a held item is refused with a list; typing `RESTORE HELD ITEMS` lets it proceed
- [ ] Restored audit entries are marked Imported and one summary entry records the backup date and count

---

## 36. Role Permissions (staging pass, one login per role)

Setup: create one login each for Supervisor, Pilot and Viewer (for example `<supervisor-user>`, `<pilot-user>`, `<viewer-user>`), plus the admin. Link the pilot login to a pilot record. Use `<staging-url>` and a second pilot record with a flight that belongs to someone else. Start from Reset to defaults in Settings > Users > Role Permissions.

### 36.1 Grid in Settings
- [ ] Role Permissions card appears below User Management, admin only
- [ ] Admin column is locked on; viewer change cells are greyed out with a reason
- [ ] At phone width every setting is reachable (one card per feature, Role selector)
- [ ] Turning a View off switches its dependent settings off; Discard restores them
- [ ] Reset to defaults asks for confirmation and restores the grid

### 36.2 Default grid, Supervisor login
- [ ] Can edit and delete any flight, and review flights and use bulk actions
- [ ] Can approve or deny another user's flight plan, but not one they submitted
- [ ] Can resolve and delete incidents, manage fleet, schedules, certifications, checklist templates and folders
- [ ] Can restore documents and place a legal hold; can dismiss alerts
- [ ] Cannot reach user management, settings, backups, API tokens or the audit log
- [ ] Cannot manage vehicle registrations

### 36.3 Default grid, Pilot login
- [ ] Can view every feature and create flights, flight plans, incidents, logs, maintenance records and events
- [ ] Can edit own flight, plan, incident, log, maintenance record, event and profile; cannot edit another user's
- [ ] Cannot delete a flight, review flights, approve plans, resolve incidents or dismiss alerts
- [ ] Can complete a maintenance schedule, check equipment out and in, update vehicle location, complete a checklist, generate a report
- [ ] Cannot create or edit schedules, manage fleet equipment, certifications or checklist templates
- [ ] Can see pilot email and phone

### 36.4 Default grid, Viewer login
- [ ] Can view every feature and export CSV
- [ ] No create, edit, delete or action buttons anywhere; direct API writes are refused
- [ ] Pilot email and phone are hidden; Generate report is unavailable
- [ ] Can still change own password and theme

### 36.5 Flipping a toggle
- [ ] As admin, set Pilot Delete flights to Own and save; as the pilot, with no new sign-in, the next request lets them delete their own flight but not another pilot's
- [ ] Set it back to None; the pilot loses delete on the next request without being signed out
- [ ] Set Pilot Edit flights to None; the pilot's edit controls disappear after a refresh

### 36.6 Pilot edits a reviewed flight
- [ ] A flight the pilot logs starts as Needs Review
- [ ] A supervisor marks it reviewed
- [ ] The pilot edits a field; the flight returns to Needs Review and the review badge count goes up
- [ ] Saving it again with no changes leaves the status alone
- [ ] A supervisor edits a reviewed flight; the status stays reviewed
- [ ] The pilot's currency does not count the flight until it is reviewed again; clear the review queue first and confirm currency recovers

### 36.7 Viewer with a view off
- [ ] Turn Flights View off for Viewer: the Flights nav entry, flight search results, flight charts, flight CSV export and flight report sections are gone
- [ ] Direct requests to flight pages and flight API routes are refused for the viewer
- [ ] Names on other records (a flight's pilot on an incident, for example) still show
- [ ] Turn the view back on; the dependent settings stay off until set again

### 36.8 Backup and restore
- [ ] Change two toggles, then Export Backup
- [ ] Reset to defaults, then restore the backup; the two changes are back
- [ ] Restore a backup taken before this feature; the grid is at defaults
- [ ] After restore, a viewer cell is still locked and the viewer still cannot change data

---

## Test Results Summary

| Section | Status | Notes |
|---------|--------|-------|
| 1. First-Run Setup | | |
| 2. Dashboard | | |
| 3. Settings — General | | |
| 4. Settings — Users | | |
| 5. Settings — Integrations | | |
| 6. Pilots | | |
| 7. Fleet — Vehicles | | |
| 8. Fleet — Batteries | | |
| 9. Fleet — Other Equipment | | |
| 10. Equipment Merge | | |
| 11. Flights | | |
| 12. Flight Import — CSV | | |
| 13. Flight Import — Excel/Airdata | | |
| 14. Flight Plans | | |
| 15. Checklists | | |
| 16. Certifications | | |
| 17. Maintenance | | |
| 18. Mission Logs | | |
| 19. Training Logs | | |
| 20. Incidents | | |
| 21. Weather Briefing | | |
| 22. ADS-B Airspace | | |
| 23. Analytics | | |
| 24. Compliance | | |
| 25. Reports | | |
| 26. Documents | | |
| 27. Photo Gallery | | |
| 28. Email Digest | | |
| 29. Audit Log | | |
| 30. Cross-References | | |
| 31. Modals | | |
| 32. Responsive | | |
| 33. Security | | |
| 34. Validation Errors | | |
| 35. Backup & Restore | | |
| 36. Role Permissions | | |
| 37. Release Staging Pass | | |

---

## 37. Release Staging Pass (hardening release)

Run on the staging instance with `TRUSTED_PROXIES` set to the proxy's address, before moving production.

- [ ] Migration 0012 applied on start; old audit entries still list
- [ ] After login through the proxy, the audit entry shows the real client address, not the proxy's
- [ ] A non-admin cannot edit their display name; an admin can. Email and theme still save
- [ ] An API token with All areas cannot read the audit log; one with the Audit Log area can
- [ ] Idle lock setting offers 30 minutes to 12 hours; locking one tab signs out the others
- [ ] Incident and mission forms refuse an unknown status or severity with a readable message
- [ ] A document upload with a duplicate file name keeps both files; the list shows the original name
- [ ] A request body over 1 MB on a normal form is refused; photo and document uploads still work
- [ ] An Excel import over 100,000 rows is refused and writes nothing
- [ ] Spreadsheet export cells starting with a space then `=` open as text
- [ ] Restore of a backup with held items needs the confirmation text
- [ ] The image scan step passes (or is understood, see the release notes)
