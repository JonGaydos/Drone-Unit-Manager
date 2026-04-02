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
- [ ] Weather thresholds configurable — **NEEDS RETEST after v2.0.7 fix**
- [ ] Weather thresholds "Reset to Defaults" button works — **NEEDS TEST**
- [ ] Sidebar config shows "Airspace" and "Activity Reports" — **NEEDS TEST**

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
- [ ] Edit vehicle details

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
- [ ] Click item — detail page loads — **MISSING: need detail pages like vehicles**
- [ ] Attachments syncing from API — **EMPTY after sync, needs investigation**
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
- [ ] Review status toggle works (needs_review → reviewed)
- [ ] Cross-reference links work (pilot, vehicle, battery names are clickable)

## 12. Flight Import — CSV
- [ ] Export flights to CSV
- [ ] Re-import the CSV — deduplication works (no double entries)

## 13. Flight Import — Airdata
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
- [ ] Add a certification type
- [ ] Assign certification to a pilot
- [ ] Set expiration date
- [ ] Expiring cert shows warning
- [ ] Certification matrix displays correctly

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

## 24. Compliance Dashboard
- [ ] Compliance score calculates
- [ ] Expired items flagged
- [ ] Attention items listed

## 25. Reports
- [ ] Generate Flight Summary report
- [ ] Generate Pilot Hours report
- [ ] Generate Equipment Utilization report
- [ ] PDF download works
- [ ] Organization logo appears on PDF
- [ ] CSV export works on each page

## 26. Documents
- [ ] Upload a document (PDF, image, etc.)
- [ ] Assign to pilot/vehicle/certification
- [ ] Document appears in folder view
- [ ] Download/view document
- [ ] File type restriction enforced (no .exe, etc.)

## 27. Photo Gallery
- [ ] Upload a photo
- [ ] Thumbnail generates
- [ ] Lightbox viewer works (click to enlarge)
- [ ] Associate photo with pilots
- [ ] Date grouping displays

## 28. Email Digest
- [ ] Configure SMTP settings (server, port, credentials)
- [ ] Send test digest — email received
- [ ] Preview digest — HTML renders
- [ ] Notification preferences — categories toggle on/off

## 29. Audit Log
- [ ] Actions logged (login, create, edit, delete)
- [ ] Filter by action type
- [ ] Filter by user
- [ ] Timestamps correct

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
| 13. Flight Import — Airdata | | |
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
