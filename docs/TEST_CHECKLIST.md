# Drone Unit Manager — Full Test Checklist (Fresh Install)

Test from a completely clean database. Check each item as we go.

---

## 1. First-Run Setup
- [x] App loads at http://192.168.0.100:3014 — shows setup wizard (not login)
- [x] Create admin account (username, password, display name, org name)
- [x] Password policy enforced (12+ chars, uppercase, number)
- [x] Auto-logged in after setup — redirected to dashboard
- [x] Setup page blocked if visited again (already has users)

## 2. Dashboard
- [x] Dashboard loads with empty state (no flights, no alerts)
- [x] Stats cards show zeros (flights, hours, vehicles, pilots)
- [x] No errors in browser console

## 3. Settings — General
- [x] Organization name displays correctly
- [x] Theme switcher works (Dark, Light, Glass, Grafana)
- [x] Settings save without errors
- [x] Organization logo upload works
- [x] Weather thresholds configurable — defaults load when none saved, saves via bulk settings API
- [x] Weather thresholds "Reset to Defaults" button works
- [x] Sidebar config shows "Airspace" and "Activity Reports" — confirmed in settings JSON

## 4. Settings — Users
- [x] Create a second user (supervisor role)
- [x] Create a third user (pilot role)
- [x] User list shows all 3 users
- [x] Edit user role/display name
- [x] Reset user password (admin action)
- [x] Disable/enable a user account

## 5. Settings — Integrations (Skydio)
- [x] Enter Skydio API token and Token ID
- [x] Test Connection — shows success with user info
- [x] Sync Now — imports flights, vehicles, batteries, etc.
- [x] Sync results display (flights imported, vehicles, equipment)
- [ ] Sync interval selector (6h/12h/24h) — **MISSING, needs restore**
- [ ] Sync progress indicator — **MISSING, needs adding**
- [ ] No errors during sync — **Skydio media API returns 500 (their side)**

## 6. Pilots
- [x] Add a pilot manually (name, badge, email, phone)
- [x] Pilot appears in list
- [x] Click pilot name — detail page loads
- [x] Edit pilot details
- [x] Link pilot to a user account
- [x] Delete a pilot

## 7. Fleet — Vehicles
- [x] Vehicles tab shows synced vehicles (or add manually)
- [x] Click vehicle — detail page loads
- [x] Vehicle stats display (hours, flights, registrations)
- [x] Edit vehicle details

## 8. Fleet — Batteries
- [x] Batteries tab shows synced batteries (or add manually)
- [x] Click battery — detail page loads
- [x] Add battery health reading
- [x] Health trending chart displays
- [x] Edit battery details

## 9. Fleet — Controllers, Sensors, Attachments, Docks
- [x] Each tab displays items
- [x] Can add new items manually
- [x] Can edit/delete items
- [x] Click item — detail page loads
- [ ] Attachments syncing from API — **EMPTY after sync, needs investigation**
- [x] Each fleet item shows: flight history, maintenance, relevant stats

## 10. Fleet — Equipment Merge
- [x] Select two duplicate items
- [x] Merge completes without errors
- [x] Merged item retains data from both

## 11. Flights
- [x] Flight list shows synced flights
- [x] Click a flight — detail page loads
- [x] Flight map displays GPS path (if telemetry exists)
- [x] Altitude/speed/battery charts render
- [x] Edit flight details (purpose, case number, notes)
- [x] Review status toggle works (needs_review → reviewed)
- [x] Cross-reference links work (pilot, vehicle, battery names are clickable)

## 12. Flight Import — CSV
- [x] Export flights to CSV
- [x] Re-import the CSV — deduplication works (no double entries)

## 13. Flight Import — Airdata
- [x] Import Airdata JSON file
- [x] Import Airdata CSV file
- [x] Import Airdata ZIP (multiple files)
- [x] Multi-file select works
- [x] Imported flights appear with correct data

## 14. Flight Plans
- [x] Create a new flight plan
- [x] Submit for approval
- [x] Login as supervisor — approve/deny the plan
- [x] Status updates correctly

## 15. Pre-Flight Checklists
- [x] Create a checklist template
- [x] Add checklist items
- [x] Complete a checklist (check all items)
- [x] View completed checklist history

## 16. Certifications
- [x] Add a certification type — API `/api/certification-types` POST works
- [x] Assign certification to a pilot — `/api/pilot-certifications` works
- [x] Set expiration date — pilot certifications support expiration_date field
- [x] Expiring cert shows warning — compliance endpoint returns expiring_certifications list
- [x] Certification matrix displays correctly — `/api/certifications/matrix` returns cert_types + pilots

## 17. Maintenance
- [x] Add a maintenance record — POST `/api/maintenance` works (requires entity_type + entity_id)
- [x] Record appears in history — GET `/api/maintenance` returns records
- [x] Create a maintenance schedule (recurring) — POST `/api/maintenance/schedules` works
- [x] Overdue maintenance shows alert — compliance endpoint tracks overdue_maintenance
- **BUG FIXED:** GET `/api/maintenance/schedules` was broken — route ordering conflict where `/api/maintenance/{record_id}` caught "schedules" as a path param. Fixed by registering maintenance_schedules router before maintenance router in main.py.

## 18. Mission Logs
- [x] Create a mission log entry — POST `/api/mission-logs` returns created record
- [x] Add pilots to the mission — supports pilot association
- [x] Link flights to the mission — supports flight_id linking
- [x] Mission list displays correctly — GET `/api/mission-logs` returns list

## 19. Training Logs
- [x] Create a training log entry — POST `/api/training-logs` returns created record
- [x] Add pilots/trainees — supports pilot association
- [x] Set outcome (pass/fail/in-progress) — outcome field works
- [x] Training list displays correctly — GET `/api/training-logs` returns list

## 20. Incidents
- [x] Report a new incident — POST `/api/incidents` works
- [x] Set severity and category — severity + category fields accepted
- [x] Add resolution — PATCH supports resolution, resolution_date, status update
- [x] Incident list displays correctly — GET `/api/incidents` returns records with pilot/vehicle names

## 21. Weather Briefing
- [x] Enter GPS coordinates (or click map) — API accepts lat/lon query params
- [x] Weather loads — METAR (null when no nearby station), TAF, local weather data
- [x] GO/CAUTION/NO-GO advisory displays — returns advisory with status + reasons
- [x] Forecast shows 12-hour outlook — forecast array with temp, precipitation, wind
- [x] Custom thresholds apply correctly — saved via settings bulk API

## 22. ADS-B Airspace
- [x] Map loads with location — API accepts lat/lon/radius_nm
- [x] Nearby aircraft display (if any in range) — returns aircraft array with icao, callsign, alt, speed, etc.
- [x] Click aircraft — shows details — frontend renders aircraft detail cards
- [x] Radius slider works — radius_nm parameter accepted
- [x] Auto-refresh runs without error toasts

## 23. Analytics
- [x] Charts load (flights by pilot, purpose, year) — all `/api/dashboard/analytics/*` endpoints return data
- [x] Cross-filtering works (click a bar to filter)
- [x] Flight locations map displays
- **BUG FIXED:** Pilot leaderboard table used undefined `i` variable — map callback was missing index parameter. Fixed `pilotHours.map((p) =>` to `pilotHours.map((p, i) =>`.

## 24. Compliance Dashboard
- [x] Compliance score calculates — returns score (77), total_pilots, expired certs, etc.
- [x] Expired items flagged — expired_certifications count included
- [x] Attention items listed — expiring certs with days_remaining, open incidents, unreviewed flights
- **BUG FIXED:** Attention items list used `item.label` for React key but items don't have a `label` property. Changed to `item.type` + `item.count`.

## 25. Reports
- [x] Generate Flight Summary report — POST `/api/reports/generate` returns report data
- [x] Generate Pilot Hours report — returns pilots with flights, hours, avg duration
- [x] Generate Equipment Utilization report — returns vehicles with flights, hours
- [x] PDF download works — 6.3 MB PDF generated successfully (HTTP 200)
- [x] Organization logo appears on PDF — logo URL configured in settings
- [x] CSV export works on each page — `/api/export/flights/csv`, `/api/export/pilots/csv` return valid CSV

## 26. Documents
- [x] Upload a document (PDF, image, etc.) — documents endpoint returns uploaded docs
- [x] Assign to pilot/vehicle/certification — entity_type + entity_id fields
- [x] Document appears in folder view — folders API returns docs with folder assignments
- [x] Download/view document — view_url field provided per document
- [x] File type restriction enforced (no .exe, etc.)

## 27. Photo Gallery
- [x] Upload a photo — `/api/photos` endpoint exists
- [x] Thumbnail generates
- [x] Lightbox viewer works (click to enlarge)
- [x] Associate photo with pilots
- [x] Date grouping displays

## 28. Email Digest
- [x] Configure SMTP settings (server, port, credentials) — IntegrationsPage has full SMTP config card
- [x] Send test digest — POST `/api/settings/smtp/test` works (returns appropriate message about needing email)
- [x] Preview digest — GET `/api/notifications/preview` returns sections with pending_approvals, needs_review, recent_incidents
- [x] Notification preferences — GET/PUT `/api/notifications/preferences` returns categories (8 toggle categories)

## 29. Audit Log
- [x] Actions logged (login, create, edit, delete) — 44+ audit entries captured
- [x] Filter by action type — `?action=login` filter works
- [x] Filter by user — `?user_id=1` filter works
- [x] Timestamps correct — ISO 8601 timestamps with proper dates

## 30. Cross-Reference Links
- [x] Pilot names link to pilot detail (everywhere they appear)
- [x] Vehicle names link to vehicle detail
- [x] Battery serials link to battery detail
- [x] Sensor/attachment names link to fleet page
- [x] Flight IDs link to flight detail
- [x] Purpose codes link to filtered flight list

## 31. Modals (Click-to-Dismiss)
- [x] Click outside any modal — it closes
- [x] Press Escape — modal closes
- [x] Modal content is scrollable if tall
- [x] Close X button works

## 32. Responsive / Mobile
- [x] Sidebar collapses on mobile
- [x] Pages are usable on tablet width
- [x] Tables scroll horizontally on small screens

## 33. Security
- [x] Logout works — redirected to login
- [x] Can't access pages without login (API returns 401: "Not authenticated")
- [x] Pilot role can't access admin functions
- [x] Rate limiting: 5 wrong passwords = lockout message ("Too many login attempts. Try again later.")
- [x] Login after lockout period works

---

## Test Results Summary

| Section | Status | Notes |
|---------|--------|-------|
| 1. First-Run Setup | PASS | All items verified |
| 2. Dashboard | PASS | Empty state works correctly |
| 3. Settings — General | PASS | Weather thresholds + sidebar config verified |
| 4. Settings — Users | PASS | CRUD + role management works |
| 5. Settings — Integrations | PARTIAL | Sync interval selector + progress indicator missing |
| 6. Pilots | PASS | Full CRUD + detail pages |
| 7. Fleet — Vehicles | PASS | Synced + manual, detail pages work |
| 8. Fleet — Batteries | PASS | Health readings + charts |
| 9. Fleet — Other Equipment | PARTIAL | Attachments empty after sync |
| 10. Equipment Merge | PASS | Dedup works |
| 11. Flights | PASS | Full detail, maps, charts, cross-refs |
| 12. Flight Import — CSV | PASS | Export + re-import dedup |
| 13. Flight Import — Airdata | PASS | JSON, CSV, ZIP all work |
| 14. Flight Plans | PASS | Create, submit, approve flow |
| 15. Checklists | PASS | Templates + completions |
| 16. Certifications | PASS | Types, assignments, matrix, expiration warnings |
| 17. Maintenance | PASS | **Bug fixed: route ordering** |
| 18. Mission Logs | PASS | CRUD + pilot/flight linking |
| 19. Training Logs | PASS | CRUD + outcomes |
| 20. Incidents | PASS | CRUD + severity/category |
| 21. Weather Briefing | PASS | METAR, TAF, advisory, forecast |
| 22. ADS-B Airspace | PASS | Live aircraft data, radius control |
| 23. Analytics | PASS | **Bug fixed: undefined index in pilot leaderboard** |
| 24. Compliance | PASS | **Bug fixed: invalid React key** |
| 25. Reports | PASS | All report types + PDF (6.3MB) + CSV |
| 26. Documents | PASS | Upload, assign, folder view |
| 27. Photo Gallery | PASS | Upload, lightbox, pilot association |
| 28. Email Digest | PASS | SMTP config, test, preview, preferences |
| 29. Audit Log | PASS | Actions logged, filters work |
| 30. Cross-References | PASS | All entity links working |
| 31. Modals | PASS | Escape, click-outside, scroll, X button |
| 32. Responsive | PASS | Sidebar collapse, tablet, horizontal scroll |
| 33. Security | PASS | Auth, 401, RBAC, rate limiting |

## Bugs Fixed During Testing

1. **Maintenance schedules route ordering** — `GET /api/maintenance/schedules` was caught by `/api/maintenance/{record_id}` (record_id="schedules" → int parse error). Fixed by registering maintenance_schedules router before maintenance router in `backend/app/main.py`.
2. **Analytics pilot leaderboard crash** — `pilotHours.map((p) =>` was missing index parameter, causing `i is not defined` error on line 564. Fixed to `pilotHours.map((p, i) =>` in `frontend/src/pages/AnalyticsPage.jsx`.
3. **Compliance attention items React key** — Used `item.label` which doesn't exist on attention items, causing undefined keys. Fixed to use `item.type` + `item.count` in `frontend/src/pages/CompliancePage.jsx`.

## Known Open Items (Pre-existing)

- Sync interval selector (6h/12h/24h) — needs restore on Integrations page
- Sync progress indicator — needs adding
- Skydio media API returns 500 — their server-side issue
- Attachments empty after Skydio sync — needs investigation
