import { useState } from 'react'
import { BookOpen, ChevronRight, ChevronDown, Search } from 'lucide-react'

const sections = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    content: [
      {
        title: 'First-Run Setup',
        body: `On first launch, a three-step setup wizard runs:

• **Organization** — Org name, your name, email address.
• **Admin Account** — Username + password (12+ chars, 1 uppercase, 1 number). No default credentials exist; the first account created becomes the administrator.
• **Optional Setup** — Upload an organization logo, configure the Skydio API integration, configure SMTP for email digests, and import existing flight logs. Each section is independently skippable — anything skipped can be set up later from Settings.

If you have a backup ZIP from another instance, choose "Restore from a backup instead?" on the setup screen. You'll need the install token printed to the container logs at first boot.`
      },
      {
        title: 'User Roles',
        body: `The application has four roles with increasing permissions:

• **Viewer** — Read-only access to all data.
• **Pilot** — Can view data and submit flight plans. Pilots can edit their own profile.
• **Supervisor** — Can approve flights, manage pilots, create/edit most records, and generate reports.
• **Admin** — Full access including user management, system settings, and audit log.`
      },
      {
        title: 'Navigating the App',
        body: 'Use the sidebar on the left to navigate between sections. The sidebar can be collapsed using the arrow at the bottom. On mobile devices, tap the menu icon in the top-left corner to open the sidebar.'
      },
      {
        title: 'Command Palette (Ctrl/Cmd+K)',
        body: `Press Ctrl+K (Cmd+K on Mac) anywhere in the app to open a global search overlay. You can also open it from the search button in the top bar. Press Escape to close.

• **Jump to a page** — Type part of a page name (Flights, Pilots, Settings, etc.) and press Enter to navigate there.
• **Search records** — Type at least two characters to search across pilots, vehicles, and flights. Results show a colored type tag for each match.
• **Type-filter chips** — When results are shown, use the All / Pilots / Vehicles / Flights chips to narrow results to one record type (page matches are always shown).
• **Recent jumps** — When the box is empty, your last few destinations appear under "Recent" for quick re-navigation.
• **Keyboard navigation** — Use the up/down arrows to move through results and Enter to open the highlighted item.`
      },
      {
        title: 'Cross-Reference Links',
        body: 'Throughout the app, pilot names, vehicle names, battery serials, sensor packages, attachments, purpose codes, and flight IDs are clickable orange links. Click any of these to navigate directly to that item\'s detail page. Purpose codes link to a filtered flights view showing all flights with that purpose.'
      },
    ]
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    content: [
      {
        title: 'Overview',
        body: 'The dashboard provides a snapshot of your drone program: total flights, flight hours, active pilots, fleet size, flights needing review, and upcoming certification expirations. Click any stat card to navigate to its detail page.'
      },
      {
        title: 'Recent Flights',
        body: 'The recent flights table shows the last 10 flights. Click a flight date to view its full detail page with telemetry, map, and equipment information.'
      },
      {
        title: 'Certification Expirations',
        body: 'Certifications expiring within 90 days are shown with color-coded badges: green (60+ days), amber (30-60 days), and red (under 30 days or expired).'
      },
    ]
  },
  {
    id: 'calendar',
    title: 'Calendar',
    content: [
      {
        title: 'Unit Calendar',
        body: `The Calendar page aggregates everything dated in your program into a single FullCalendar view. It pulls in:

• **Flights** — A per-day count badge (e.g. "3 flights"); click it to open the Flights page.
• **Missions** — Entries from the Mission Log on their mission date.
• **Training** — Entries from the Training Log on their training date.
• **Maintenance due** — The next-due date of each recurring maintenance schedule.
• **Cert expirations** — Each pilot certification's expiration date, labeled with the pilot and certification name.
• **Events and leave** — Manual entries you add yourself (see below).

Each category has a colored checkbox above the calendar to show or hide that type. Clicking a flight, mission, training, maintenance, or certification item navigates to the relevant page.`
      },
      {
        title: 'Views',
        body: 'Switch between Month, Week, and List views using the buttons in the top-right of the calendar. Use prev/next and Today to move through the date range; only items within the visible range are loaded.'
      },
      {
        title: 'Adding Events and Leave',
        body: `Click "Add event / leave" to create a manual entry. Choose a category (Event or Leave), a title, a start date, an optional end date (for multi-day entries), and optional notes.

Any signed-in user, including pilots, can add their own events and leave. You can edit or delete an entry you created; supervisors and admins can edit or delete any manual entry. The other aggregated items (flights, missions, training, maintenance, certifications) are read-only on the calendar and are managed from their own pages.`
      },
    ]
  },
  {
    id: 'flights',
    title: 'Flights',
    content: [
      {
        title: 'Viewing Flights',
        body: 'The Flights page shows all recorded flights with filtering by date range, pilot, vehicle, purpose, and review status. Use the text search to find flights by pilot name, vehicle, purpose, or location.'
      },
      {
        title: 'Adding Flights Manually',
        body: 'Click "Add Flight" to record a flight manually. Select the pilot, vehicle, date, duration, purpose, and optionally a takeoff address and case number.'
      },
      {
        title: 'Reviewing Flights',
        body: 'Flights imported from the Skydio API arrive with "Needs Review" status. Supervisors can review individual flights via the inline edit button, or use "Approve All" to mark all pending flights as reviewed.'
      },
      {
        title: 'Flight Detail',
        body: 'Click a flight ID to see the full detail page. If telemetry data was synced, you\'ll see an interactive map with the flight path and charts for altitude, speed, and battery level over time.'
      },
    ]
  },
  {
    id: 'fleet',
    title: 'Fleet Management',
    content: [
      {
        title: 'Vehicles',
        body: 'The Fleet page shows all drones, batteries, and controllers. Click any item to view its detail page with flight history, maintenance records, and specifications.'
      },
      {
        title: 'Batteries',
        body: 'Battery records track serial numbers, cycle counts, and health status. Battery assignments to flights are tracked automatically when imported from the API.'
      },
      {
        title: 'Controllers',
        body: 'Remote controller inventory is tracked separately. Controllers can be assigned to specific vehicles or shared across the fleet.'
      },
      {
        title: 'Components',
        body: 'Component-level tracking (propellers, gimbals, cameras) lets you monitor individual parts with flight hours, installation dates, and warranty information.'
      },
      {
        title: 'Equipment Checkout',
        body: 'The equipment checkout system provides chain-of-custody tracking. Check equipment out to a pilot, and check it back in when returned.'
      },
      {
        title: 'Equipment Dropdowns',
        body: 'When adding or editing a flight, equipment fields (battery, sensor package, attachments) show a dropdown of existing Fleet inventory. You can type to search or select from the list. Typing a new serial number automatically creates a Fleet record for it.'
      },
      {
        title: 'Merging Duplicates',
        body: 'If duplicate equipment records exist (e.g., two entries for the same battery), use the merge button (icon) in Fleet > Batteries/Sensors/Attachments. Select the duplicate to absorb — all flight references will be updated and the duplicate deleted.'
      },
      {
        title: 'Battery Health Tracking',
        body: 'Each battery has a health history chart showing health percentage and cycle count over time. Go to Fleet > click a battery > Health History section. Use "Record Reading" to manually add health data points. Health readings are also recorded automatically during Skydio API sync.'
      },
    ]
  },
  {
    id: 'checkouts',
    title: 'Equipment Checkouts',
    content: [
      {
        title: 'Checking Equipment Out',
        body: `The Equipment Checkouts page provides chain-of-custody tracking. Click "Check Out" and choose the equipment type (vehicle, battery, controller, dock, sensor, or attachment), the specific item, and the pilot who is taking it. You can optionally set an expected return date and notes.

The checkout defaults to the logged-in user as the holder, but you can pick any pilot (for example, a supervisor recording a checkout on someone's behalf). Equipment that is already checked out cannot be checked out again until it is returned.`
      },
      {
        title: 'Checking Equipment Back In',
        body: 'In the "Currently Out" list, click "Check In" on a row, confirm who returned the item, and add optional notes. The record is then marked returned with a timestamp. Both the user who entered the record and the pilot who held or returned the item are captured in the audit log.'
      },
      {
        title: 'Active and Returned Records',
        body: 'The page shows a "Currently Out" section with everything still checked out, and a History section. Toggle "Show returned" to include completed (returned) records in the History list. Supervisors and admins can permanently delete a checkout record.'
      },
    ]
  },
  {
    id: 'locations',
    title: 'Drone Locations',
    content: [
      {
        title: 'Last-Known Location',
        body: `The dashboard includes a Locations tile listing each active drone and its last-known location. A drone's location is the more recent of an active equipment checkout (shown as "with <pilot>") or a manually set location.`
      },
      {
        title: 'Setting a Location',
        body: `Use the "Set location…" dropdown on each drone in the dashboard Locations tile to set its location to either a named place or a specific pilot. Setting a location manually updates the last-known location immediately.

The list of named places (for example North, Central, South) is configured by admins in Settings under Drone Locations. Pilots are always available as location targets in addition to the configured places.`
      },
    ]
  },
  {
    id: 'logs',
    title: 'Mission Log & Training Log',
    content: [
      {
        title: 'Mission Log',
        body: `The Mission Log records non-flight missions and operations. Each entry has a date, title, reason/purpose, location, case number, drone used, man-hours, optional start/end times, description, and notes. You can attach multiple pilots to a mission, each with a role (PIC, Observer, Spotter, Visual Observer, Support) and hours. Pilots and above can add, edit, import, and delete entries; use the search box and date/pilot filters to find missions, and Export CSV to download the list.`
      },
      {
        title: 'Training Log',
        body: 'The Training Log records training events. Each entry has a date, training type (e.g. Recurrent), title, location, instructor, man-hours, optional start/end times, and a drone used. Like missions, training entries support multiple pilots with a role and hours each (the Student role is also available for training).'
      },
    ]
  },
  {
    id: 'pilots',
    title: 'Pilots',
    content: [
      {
        title: 'Pilot Profiles',
        body: 'Each pilot has a profile with contact information, badge number, photo, and status (active/inactive). Click a pilot\'s name to view their full profile with flight history, certifications, and training records.'
      },
      {
        title: 'Pilot Currency',
        body: `Currency rules define how many flight hours (and optionally how many flights) a pilot must log within a rolling period to stay current (e.g., 5 hours in 90 days).

Admins create rules from Settings → Currency Rules. Rules can be scoped to a specific vehicle model or apply across all aircraft. Once at least one active rule exists, each pilot's detail page shows a Currency Status section with per-rule progress, current/lapsed badge, and the projected expiry date (the date the pilot would lapse if they don't fly again).`
      },
      {
        title: 'Needs Attention',
        body: `Each pilot's detail page has a Needs Attention card that aggregates the items most likely to require action for that pilot:

• **Lapsed currency** — Any active currency rule the pilot is not current on, shown in red.
• **Expired certifications** — Certifications past their expiration date, shown in red.
• **Expiring certifications** — Certifications expiring within 30 days, shown in amber with the days remaining.

When nothing is outstanding, the card shows an "All clear" message. The count of items appears in the card header.`
      },
    ]
  },
  {
    id: 'certifications',
    title: 'Certifications',
    content: [
      {
        title: 'Certification Types',
        body: 'Create custom certification types from the Settings page (e.g., Part 107, TRUST, Night Waiver). Each type can have custom status labels and renewal periods.'
      },
      {
        title: 'Tracking Expirations',
        body: 'The Certifications page shows a matrix of all pilots and their certification statuses. Color-coded badges indicate valid, expiring soon, or expired status. The system generates alerts for upcoming expirations.'
      },
    ]
  },
  {
    id: 'maintenance',
    title: 'Maintenance',
    content: [
      {
        title: 'Maintenance Records',
        body: 'Record maintenance events for any vehicle, battery, controller, or dock — or pick "Other" for items not tied to equipment (e.g., an FAA authorization renewal). Include the date, description, technician, and notes. Use the paperclip on any history row to attach related documents.'
      },
      {
        title: 'Schedules & Tasks',
        body: 'Set up recurring maintenance schedules (monthly, quarterly, yearly, every 2 or 3 years) or one-time tasks with a specific due date via Add Schedule / Task. The system tracks when each item is next due and generates alerts when overdue. Marking a one-time task complete logs a maintenance record and closes the task; recurring schedules roll forward to the next due date.'
      },
    ]
  },
  {
    id: 'weather',
    title: 'Weather',
    content: [
      {
        title: 'Weather Briefing',
        body: 'The Weather page provides a live aviation weather briefing using METAR and TAF data. Enter a location (airport code, city, or GPS coordinates) to get current conditions.'
      },
      {
        title: 'Default Location',
        body: 'On load, the Weather page pre-populates to your organization Default Location (set in Settings). If no Default Location is configured, it falls back to the White House in Washington D.C. so the page always has a sensible center. Your recently searched locations are remembered and shown as quick-pick buttons under Recent Locations.'
      },
      {
        title: 'GO/NO-GO Advisory',
        body: 'Based on your configured weather thresholds (wind speed, visibility, cloud ceiling), the system provides a GO, CAUTION, or NO-GO advisory. Configure thresholds from the Settings page.'
      },
    ]
  },
  {
    id: 'airspace',
    title: 'Airspace (ADS-B)',
    content: [
      {
        title: 'Live Aircraft Map',
        body: 'The Airspace page shows a live map of nearby manned aircraft using ADS-B data from airplanes.live. Click anywhere on the map to set your search center — a blue circle shows the search radius. Aircraft markers are color-coded by altitude: red (below 400ft, drone zone), orange (400-1000ft), yellow (1000-5000ft), blue (5000-15000ft), gray (above 15000ft).'
      },
      {
        title: 'Using the Map',
        body: 'Click a location on the map to start scanning. Adjust the radius (25-200 miles) and refresh interval (5-30 seconds or off) using the controls at the top. Click any aircraft marker to see its callsign, altitude, speed, heading, squawk code, and aircraft type. The aircraft count and last refresh time are shown in the top bar.'
      },
      {
        title: 'Default Location and Recent Chip',
        body: 'On load, the map centers on your organization Default Location (set in Settings), falling back to the White House if none is configured. After you click a point, a "Recent" chip appears in the control bar so you can jump straight back to your last selected location.'
      },
    ]
  },
  {
    id: 'flight-plans',
    title: 'Flight Plans & Checklists',
    content: [
      {
        title: 'Flight Plan Submission',
        body: 'Pilots can submit flight plans for supervisor approval. Include the mission objective, location, date/time, equipment, and weather conditions.'
      },
      {
        title: 'Pre-Flight Checklists',
        body: 'Create custom pre-flight checklist templates from the Checklists page. Pilots complete checklists before each flight, and completed checklists are stored for compliance records.'
      },
    ]
  },
  {
    id: 'documents',
    title: 'Documents & Photos',
    content: [
      {
        title: 'Document Storage',
        body: 'Upload and organize documents in folders. Use the Upload button on the Documents page to add standalone files (FAA authorizations, forms, etc.) directly into the selected folder. System folders (General, Certifications, Insurance, Maintenance, Reports) are created automatically. Create custom folders for additional organization. Documents uploaded from pilot profiles and certifications are auto-filed.'
      },
      {
        title: 'Photo Gallery',
        body: 'Upload photos from flights, training, and events. Photos are organized by date with a lightbox viewer. Associate pilots with photos for easy reference.'
      },
      {
        title: 'Linking Photos to Flights and Incidents',
        body: 'Flight and incident detail pages have a Photos section listing attached photos. Linking and unlinking photos (attaching existing gallery photos to a flight or incident, or detaching them) requires Supervisor or Admin. Pilots and viewers can see linked photos but cannot attach or detach them.'
      },
    ]
  },
  {
    id: 'reports',
    title: 'Reports & Analytics',
    content: [
      {
        title: 'PDF Reports',
        body: `Generate professional PDF reports with your organization's logo and branding. Available report types:

• Flight Summary — All flights within a date range
• Pilot Hours — Flight hours by pilot
• Equipment Utilization — Usage statistics per vehicle
• Pilot Activity Summary — Per-pilot activity report
• Annual Unit Report — Yearly program summary
• Certifications — Current certification status
• Battery Status — Battery health and usage
• Maintenance History — Maintenance records by date range`
      },
      {
        title: 'CSV Export',
        body: 'Every list page supports CSV export. Click the "Export CSV" button to download the current view as a spreadsheet.'
      },
      {
        title: 'Analytics',
        body: 'The Analytics page provides interactive Power BI-style charts. Click any chart element (a pilot, year, purpose, or vehicle) to cross-filter all other charts. The map shows all flight locations.'
      },
      {
        title: 'GPX and KML Export',
        body: 'Flight paths can be exported as GPX (for GPS devices) or KML (for Google Earth) from the flight detail page. These buttons appear when the flight has telemetry data. The exported files contain the full GPS track with altitude and speed data.'
      },
    ]
  },
  {
    id: 'compliance',
    title: 'Compliance',
    content: [
      {
        title: 'Compliance Score',
        body: 'The Compliance page calculates a 0-100 score based on certification status, registration status, maintenance compliance, pilot currency, and operating authority. Each category shows what\'s compliant and what needs attention.'
      },
      {
        title: 'Operating Authority',
        body: `The Operating Authority page tracks the unit's own COAs and Part 107 waivers, with issue and expiry dates, a status badge, and attached documents. Admins and Supervisors can add and edit; Pilots and Viewers have read-only access.

An authority within 90 days of expiry takes 5 points off the compliance score. An expired authority marked "Expiry grounds the unit" caps the score at 50 no matter how clean everything else is, with the reason shown under the score, because a green score while the unit is unauthorised would be misleading. Untick that box for an authority whose lapse restricts one kind of operation rather than grounding the unit (a night waiver, for example); an expired one of those takes 10 points off instead.

Set a record's status to Superseded (renewed by a newer authority) or Not applicable (the unit no longer operates under it) to keep it on file for the reports without it counting against compliance. A unit with no authorities on file is scored exactly as before.

Authorities appear in the Annual Unit Report (those held during the reporting period) and in the Certifications report.`
      },
    ]
  },
  {
    id: 'incidents',
    title: 'Activity Reports (Incidents)',
    content: [
      {
        title: 'Incident Reporting',
        body: 'Report incidents including crashes, near-misses, equipment failures, and successes (missing persons found, suspects located, evidence collected). Each report includes severity level, description, corrective actions, and can be linked to flights, pilots, and vehicles.'
      },
    ]
  },
  {
    id: 'integrations',
    title: 'Integrations & Import',
    content: [
      {
        title: 'Drone Provider APIs',
        body: 'The Integrations tab in Settings manages connections to drone manufacturer APIs. Currently Skydio is supported, with DJI, BRINC, Parrot, and Autel planned. Each provider has credential fields, Test Connection, Sync Now, Full Sync, and Sync Telemetry (10) buttons. Sync Now fetches new flights and automatically syncs telemetry. Sync Telemetry (10) fetches detailed flight path data for up to 10 flights at a time.'
      },
      {
        title: 'Skydio Cloud API',
        body: `To connect to the Skydio Cloud API:

1. Log into Skydio Cloud at cloud.skydio.com
2. Go to Settings > Integrations > API Tokens
3. Create a token with read access to: Flights, Flight Telemetry, Vehicles, Batteries, Controllers, Users, Attachments, Sensor Packages
4. In Drone Unit Manager, go to Settings > Integrations tab
5. Enter the API Token and Token ID
6. Click "Test Connection", then "Sync Now"

For automatic pilot matching, ensure each pilot's profile has their Skydio account email address.`
      },
      {
        title: 'Sync Status and Disconnect',
        body: `Expanding the Skydio card shows a persistent sync-status block that updates after each sync without a page reload:

• **State** — Whether a sync is currently running (incremental, full, or telemetry) or idle.
• **Last synced** — When the last sync ran, as a relative time plus the exact timestamp.
• **Next sync** — The estimated time until the next scheduled auto-sync, when an auto-sync interval is set.
• **Last run** — A summary of the most recent run (new flights, vehicles, batteries, controllers, and error count) with a colored status dot: green for success, amber for a partial run, and red for a failure. If there were errors, the first one is shown with a "+N more" count.

The card also has a **Disconnect** button. Disconnecting clears the stored Skydio token so syncing stops; you can reconnect later by re-entering the token.`
      },
      {
        title: 'Flight Log Import',
        body: `Import flight data from multiple sources via Settings > Integrations tab:

• **Skydio CSV** — Flight records exported from Skydio Cloud
• **Excel** — Spreadsheets with "Skydio" and "Pilot Info" sheets
• **DJI .txt** — DJI Go 4 flight log text files
• **Litchi CSV** — Litchi flight log exports
• **Airdata CSV** — Rich 52-column exports with gimbal, RC inputs, battery temperature, flight mode
• **Airdata JSON** — Single flight JSON exports from Airdata.com
• **Airdata ZIP** — Bulk export of all flights from Airdata.com (ZIP of JSON files)
• **Parrot / ANAFI** — GUTMA JSON flight logs

Format is auto-detected, or you can pick a specific format. Select multiple files at once using Ctrl+click or Shift+click. The app processes them sequentially with live progress tracking and automatic deduplication.`
      },
      {
        title: 'SMTP Email',
        body: 'Configure SMTP settings in the Integrations tab to enable email digest notifications. Enter your SMTP host, port, username, password, from address, and TLS settings. Use the "Send Test Email" button to verify the configuration.'
      },
      {
        title: 'Email Digest Notifications',
        body: 'Once SMTP is configured, each user can set up email digest preferences in Settings > General. Choose daily or weekly frequency, preferred send time, and which categories to include: pending flight plan approvals, flights needing review, expiring certifications, expiring registrations, overdue maintenance, assigned missions, overdue equipment checkouts, and recent incidents.'
      },
    ]
  },
  {
    id: 'settings',
    title: 'Settings & Admin',
    content: [
      {
        title: 'Settings Tabs',
        body: 'The Settings page is organized into tabs: General (organization info, default location, weather thresholds, certification labels, mission purposes, drone locations, currency rules, sidebar config, backup and restore), Users (change password, user management), and Integrations (provider APIs, SMTP, flight log import).'
      },
      {
        title: 'Organization Settings',
        body: 'Configure your organization name, logo, and timezone from the Settings page.'
      },
      {
        title: 'Default Location',
        body: 'The Default Location (General tab, admin only) sets the organization\'s map center. Type an address or place name and click Search to geocode it, then save it as the default. This location pre-populates the Weather page, the Airspace map, and the dashboard weather tile. If unset, the app falls back to the White House in Washington D.C.'
      },
      {
        title: 'Sidebar Configuration',
        body: `Admins can customize the left navigation from Settings (General tab):

• **Visibility** — Toggle the checkbox next to any item to show or hide it in the sidebar.
• **Reorder** — Drag items by the grip handle to reorder them, or use the up/down arrows for fine control.
• **Group headers** — Toggle whether section group headers (Overview, Flight Ops, etc.) are shown.

Click "Save Sidebar Config" to apply.`
      },
      {
        title: 'Drone Locations',
        body: 'The Drone Locations list (General tab, admin only) defines the named places that appear in the dashboard Locations tile\'s "Set location" dropdown (for example North, Central, South). Add, edit, or remove places and save. Pilots are always selectable as locations in addition to these places.'
      },
      {
        title: 'User Management',
        body: 'Admins can create, edit, and deactivate user accounts from Settings > Users. Assign roles and link users to pilot profiles for permissions-based access.'
      },
      {
        title: 'Audit Log',
        body: 'The Audit Log (admin only) shows a complete history of all actions taken in the system: who did what, when, and what changed. Use it for accountability and compliance auditing.'
      },
    ]
  },
  {
    id: 'backup',
    title: 'Backup & Restore',
    content: [
      {
        title: 'In-App Backup',
        body: `Admins can download a full backup from Settings → General → Backup & Restore. Click "Export Backup" to download a ZIP containing every table as JSON plus all uploaded files. A checkbox controls whether flight telemetry (GPS, altitude, speed) is included; telemetry can be very large, so it is optional. The export is admin-only and recorded in the audit log.`
      },
      {
        title: 'Automated Backups',
        body: 'Admins can also enable daily automated backups (Settings → General → Automated Backups). Set how many backups to keep and the hour of day to run. Backups are written under the data volume\'s backups folder; schedule changes take effect after the next app restart.'
      },
      {
        title: 'Restoring From Backup',
        body: `Restore is done on a fresh install. On the setup screen, choose "Restore from a backup instead?", upload the backup ZIP, and enter the one-time install token printed to the container logs at first boot. After a successful restore the install token is retired.

Once any user account exists, the in-app restore option is no longer shown; restoring into an existing install is an operator task done against the backup API with an admin token rather than through the app.`
      },
      {
        title: 'Filesystem Backup (Fallback)',
        body: `If you prefer to snapshot the data directory directly, stop the container and copy these from the /app/data volume:

• drone_unit_manager.db (main database)
• telemetry.db (flight telemetry)
• uploads/ (documents and photos)

Restart the container when done. On startup the application runs any pending schema migrations automatically before serving.`
      },
    ]
  },
]

export default function UserManualPage() {
  const [expandedSections, setExpandedSections] = useState(new Set(sections.map(s => s.id)))
  const [search, setSearch] = useState('')

  const toggleSection = (id) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filteredSections = search
    ? sections.filter(s =>
        s.title.toLowerCase().includes(search.toLowerCase()) ||
        s.content.some(c =>
          c.title.toLowerCase().includes(search.toLowerCase()) ||
          c.body.toLowerCase().includes(search.toLowerCase())
        )
      )
    : sections

  const renderMarkdown = (text) => {
    return text.split('\n').map((line, i) => {
      const lineKey = `line-${i}-${line.slice(0, 20)}`
      if (line.startsWith('• **')) {
        const match = line.match(/^• \*\*(.+?)\*\*(.*)$/)
        if (match) {
          return (
            <div key={lineKey} className="flex gap-2 ml-2 mt-1">
              <span className="text-muted-foreground">•</span>
              <span><strong className="text-foreground">{match[1]}</strong>{match[2]}</span>
            </div>
          )
        }
      }
      if (line.startsWith('• ')) {
        return (
          <div key={lineKey} className="flex gap-2 ml-2 mt-1">
            <span className="text-muted-foreground">•</span>
            <span>{line.slice(2)}</span>
          </div>
        )
      }
      if (line.match(/^\d+\./)) {
        return (
          <div key={lineKey} className="ml-2 mt-1">{line}</div>
        )
      }
      if (line.trim() === '') return <div key={lineKey} className="h-2" />
      return <span key={lineKey}>{line} </span>
    })
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center text-primary">
          <BookOpen className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Manual</h1>
          <p className="text-sm text-muted-foreground">Complete guide to using Drone Unit Manager</p>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search manual..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-secondary border border-border rounded-lg text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {filteredSections.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          No sections match your search.
        </div>
      )}

      {filteredSections.map(section => (
        <div key={section.id} className="bg-card border border-border rounded-xl overflow-hidden">
          <button
            onClick={() => toggleSection(section.id)}
            className="w-full flex items-center justify-between p-5 text-left hover:bg-muted/30 transition-colors"
          >
            <h2 className="text-lg font-semibold text-foreground">{section.title}</h2>
            {expandedSections.has(section.id) ? (
              <ChevronDown className="w-5 h-5 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="w-5 h-5 text-muted-foreground shrink-0" />
            )}
          </button>
          {expandedSections.has(section.id) && (
            <div className="px-5 pb-5 space-y-4">
              {section.content.map((item) => (
                <div key={item.title}>
                  <h3 className="text-sm font-semibold text-foreground mb-1.5">{item.title}</h3>
                  <div className="text-sm text-muted-foreground leading-relaxed">
                    {renderMarkdown(item.body)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
