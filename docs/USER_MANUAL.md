# Drone Unit Manager — User Manual

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard](#2-dashboard)
3. [Settings](#3-settings)
4. [Pilots](#4-pilots)
5. [Fleet Management](#5-fleet-management)
6. [Flights](#6-flights)
7. [Certifications](#7-certifications)
8. [Pre-Flight Operations](#8-pre-flight-operations)
9. [Mission and Training Logs](#9-mission-and-training-logs)
10. [Maintenance](#10-maintenance)
11. [Activity Reports](#11-activity-reports)
12. [Compliance Dashboard](#12-compliance-dashboard)
13. [Analytics](#13-analytics)
14. [Reports](#14-reports)
15. [Photo Gallery](#15-photo-gallery)
16. [Document Storage](#16-document-storage)
17. [Audit Log](#17-audit-log)
18. [User Roles](#18-user-roles)
19. [Mobile Access](#19-mobile-access)
20. [Backup and Recovery](#20-backup-and-recovery)

---

## 1. Getting Started

### 1.1 First-Time Setup

When you launch Drone Unit Manager for the first time, a setup wizard appears. There are no default credentials — you create the first admin account during setup.

1. Enter your organization name (optional but recommended for reports).
2. Enter your name.
3. Click Continue.
4. Choose a username and password. The password must be at least 12 characters with one uppercase letter and one number.
5. Click Create Account. You are logged in automatically.

### 1.2 Logging In

Navigate to your Drone Unit Manager URL in any web browser. Enter your username and password. Both are case-sensitive. If you enter the wrong password more than 5 times within 60 seconds, you will be temporarily locked out.

### 1.3 Navigating the Interface

The sidebar on the left provides access to all sections of the application. Click any item to navigate to that page. The sidebar can be collapsed by clicking the arrow at the bottom for more screen space. Your current page is highlighted with a purple accent.

### 1.4 Themes

Click the palette icon in the top-right corner to switch between visual themes: Dark (default), Light, Glass (frosted transparency), and Grafana (operations center style).

---

## 2. Dashboard

The dashboard is your home page and provides an at-a-glance overview of your drone program.

### 2.1 Overview Cards

Six cards at the top show key metrics: Total Flights, Total Flight Hours, Active Pilots, Fleet Size, Flights Needing Review, and Upcoming Certification Expirations. Each card is clickable and navigates to the relevant page.

### 2.2 Recent Flights

A table shows the 10 most recent flights with date, pilot, vehicle, purpose, duration, and review status. Click any flight to view its details.

### 2.3 Fleet Overview

Shows total fleet flight hours, your top 3 most-used vehicles by hours, total batteries in service, and any overdue maintenance items.

### 2.4 Upcoming Certifications

Lists pilot certifications expiring within the next 90 days, color-coded by urgency: green (60+ days), amber (30-60 days), red (under 30 days).

### 2.5 Upcoming Maintenance

Shows maintenance items that are due soon, with days remaining and color-coded urgency indicators.

---

## 3. Settings

The Settings page is accessible to administrators only and controls organization-wide configuration.

### 3.1 Organization Settings

Enter your organization name and upload a logo. The logo appears on generated PDF reports.

### 3.2 Skydio API Configuration

Connect to the Skydio Cloud API to automatically import flights, vehicles, batteries, and controllers.

1. Log into Skydio Cloud and create an API token with read permissions.
2. Enter the API Token and Token ID in the fields provided.
3. Select a sync interval (Manual Only, Daily, or Weekly).
4. Click Test Connection to verify.
5. Click Sync All to perform a full import.

Ensure all pilots have email addresses in their profiles before syncing. The system matches Skydio user emails to local pilot records to automatically assign pilots to flights.

### 3.3 Importing Data from Excel

Upload an Excel spreadsheet containing flight data exported from Skydio or another source. The spreadsheet must have a sheet named "Skydio" with specific column headers. Click the format requirements link below the upload button to see the required column names. An optional "Pilot Info" sheet imports certification data.

### 3.4 User Management

Create, edit, and manage user accounts.

1. Click Add User and enter a username, password, display name, and role.
2. Optionally link the user to a pilot profile so the system knows which pilot they are.
3. Use the edit button on existing users to change their role, display name, or pilot link.
4. Toggle users active or inactive as needed.

### 3.5 Sidebar Configuration

Toggle which sidebar items are visible for all users. Use the up and down arrows to reorder items. Changes apply to all users in the organization.

### 3.6 Weather Thresholds

Customize the GO, CAUTION, and NO-GO limits for the weather briefing tool. Set thresholds for sustained wind, gusts, visibility, ceiling, temperature, and precipitation based on your organization's operating procedures.

### 3.7 Certification Status Labels

Rename the default certification status labels to match your organization's terminology. For example, rename "complete" to "Certified" or "pending" to "In Progress."

### 3.8 Mission Purposes

Define custom purpose categories that appear in mission log and flight purpose dropdowns. Add or remove purposes as needed.

---

## 4. Pilots

### 4.1 Adding Pilots

Go to the Pilots page and click Add Pilot. Enter the pilot's first name, last name, email address, personal cell phone, work cell phone, badge number, and any notes. The email address is critical for matching API-synced flights to the correct pilot.

### 4.2 Pilot Profiles

Click any pilot's name to view their full profile. The profile shows contact information, flight statistics, certifications, flight history, currency status, performance analytics, and uploaded documents. Administrators and supervisors can edit any pilot's profile. Pilots can edit only their own profile.

### 4.3 Certifications on Profiles

The certifications section on a pilot's profile shows all assigned certifications with their status, issue date, and expiration date. This data mirrors what appears on the Certifications matrix page.

### 4.4 Flight History

A table of all flights associated with this pilot, showing date, vehicle, purpose, duration, battery, and location. Click any flight to view its detail page.

### 4.5 Currency Status

If currency rules are configured in the system, this section shows whether the pilot meets each rule's requirements. Green indicates current, red indicates lapsed. Currency rules define how many flight hours or flights a pilot must complete within a given time period to remain current on a specific equipment type.

### 4.6 Performance Analytics

Charts showing the pilot's flights by month and flights by purpose, along with summary statistics for total flights, flight hours, training hours, mission hours, and incidents.

---

## 5. Fleet Management

### 5.1 Vehicles

The Fleet page shows all tracked vehicles with columns for nickname, manufacturer, model, serial number, FAA registration, and status. Click any vehicle name to view its detail page with flight history, equipment history, maintenance records, FAA registration tracking, checkout status, components, and documents.

### 5.2 Batteries

The Batteries tab lists all batteries with serial number, nickname, manufacturer, model, vehicle model, cycle count, health percentage, and status. Click a battery to see its detail page with flight history, maintenance records, and documents.

### 5.3 Controllers

The Controllers tab shows all controllers. Click a controller to view its detail page.

### 5.4 Sensors and Accessories

The Sensors and Attachments tabs show sensor packages and mounted accessories tracked by the system. These are typically populated automatically through API sync.

### 5.5 FAA Registration Tracking

On a vehicle's detail page, the FAA Registration section tracks registration history. Add a registration with the registration number and date. The system automatically calculates the expiry date (2 years from registration). The most recent registration determines the "Next Due" date displayed on the fleet overview.

### 5.6 Equipment Checkout

On a vehicle's detail page, use the Check Out button to record who has the equipment, its condition when taken, and the expected return date. When the equipment is returned, click Check In and record the return condition. The checkout history provides a chain of custody audit trail.

### 5.7 Components

Track individual components installed on a vehicle (propellers, gimbals, cameras, motors). Record installation date, flight hours, maximum rated hours, warranty expiry, and replacement cost. This helps predict when components need replacement.

---

## 6. Flights

### 6.1 Flight List

The Flights page shows all flights in a paginated table (100 per page). Filter by status (All, Needs Review, Reviewed), date range, pilot, vehicle, or purpose. Click the Flight ID to open a flight's detail page.

A small colored dot next to the status badge indicates telemetry sync status: green means telemetry data has been fetched, gray means it is pending.

### 6.2 Reviewing API-Synced Flights

Flights imported from the Skydio API arrive with a "Needs Review" status. They include the date, pilot (if email matched), vehicle, duration, and location, but may lack a purpose code since Skydio does not track flight purpose. Use the inline edit button (pencil icon) to assign a purpose and verify the pilot, then approve the flight.

### 6.3 Adding Manual Flights

Click Add Flight to manually create a flight record. This is useful for drones without API integration. Enter the date, pilot, vehicle, purpose, duration, and any other available information.

### 6.4 Flight Detail and Telemetry

The flight detail page shows all metadata, a map with the flight path (if telemetry is available), and charts for altitude, speed, and battery percentage over time. Altitude is displayed in feet and speed in miles per hour.

### 6.5 Refreshing from API

On any API-synced flight, click Refresh from API to fetch the latest data from Skydio, including telemetry points, equipment details, and pilot information. This updates the flight with max altitude, max speed, and full telemetry charts.

### 6.6 Syncing Telemetry in Bulk

In Settings under the Skydio Cloud API section, the Sync Telemetry button fetches telemetry for 10 flights at a time that do not yet have telemetry data. Press the button repeatedly to process more flights. The button shows how many flights remain.

### 6.7 Exporting Flight Data

Click Export CSV on the flights page to download all flight data as a comma-separated values file compatible with Excel and other spreadsheet applications.

---

## 7. Certifications

### 7.1 Certification Matrix

The Certifications page displays a matrix showing every active pilot and their status on each certification type. Color-coded status badges make it easy to identify gaps at a glance.

### 7.2 Adding Certification Types

Click the Cert Types tab to manage certification categories. Add new types with a name, category (FAA, NIST, Equipment, Insurance, Training, Custom), and whether the certification has an expiration date.

### 7.3 Assigning Certifications

Click any cell in the matrix to assign or update a pilot's certification. Fill in the status, issue date, expiration date, and certificate number. You can also attach supporting documents directly from this modal.

### 7.4 Reordering Columns

Administrators can reorder certification type columns using the left and right arrow buttons on the column headers. The order is saved and persists across sessions.

### 7.5 Attaching Documents

When editing a certification assignment, use the document upload section at the bottom of the modal to attach certificates, licenses, or other supporting files. These documents are automatically filed in the Certifications folder in Document Storage.

### 7.6 Custom Status Labels

In Settings, administrators can rename the default status labels (not_issued, pending, complete, active, expired, not_eligible) to match the organization's preferred terminology.

---

## 8. Pre-Flight Operations

### 8.1 Weather Briefing

The Weather page provides a live pre-flight weather assessment for any location.

1. Click a point on the map or enter GPS coordinates manually.
2. Click Check Weather.
3. The system displays a GO, CAUTION, or NO-GO advisory based on your organization's configured thresholds.
4. Review current conditions (wind, gusts, temperature, visibility, ceiling, precipitation), the nearest METAR station data, and a 12-hour forecast.

The raw METAR and TAF strings are available in expandable sections for reference.

### 8.2 Flight Plans

The Flight Plans page manages a pre-flight approval workflow.

1. A pilot submits a flight plan with the date, location, vehicle, purpose, estimated duration, and maximum altitude (0-400 feet).
2. A supervisor reviews the plan and approves or denies it (with a reason if denied).
3. The submitter can edit their plan while it is pending approval.
4. Administrators can edit any plan regardless of its status.

The sidebar shows a badge count of pending flight plans requiring review.

### 8.3 Pre-Flight Checklists

Administrators and supervisors create checklist templates with named items that can be marked as required. Pilots complete checklists before flights by checking off each item and optionally adding notes. Completed checklists are stored with the date, pilot, vehicle, and pass/fail status.

---

## 9. Mission and Training Logs

### 9.1 Mission Log

The Mission Log tracks operational deployments including the date, title, reason, location, case number, drone used, and participating pilots with individual roles and man-hours. This is separate from flight time tracking and is intended for documenting the overall mission, not just the airborne portion.

### 9.2 Training Log

The Training Log records training sessions with the type (Initial, Recurrent, Proficiency, Special), instructor, objectives, outcome, and participating pilots with hours. This provides documentation for ongoing training requirements.

### 9.3 Man-Hours Tracking

Both logs track man-hours per pilot per entry. These hours roll up into the Pilot Activity Summary report, which combines flight hours, mission hours, and training hours for each pilot.

---

## 10. Maintenance

The Maintenance page shows three sections on a single view.

### 10.1 Adding Maintenance Records

Click Add Maintenance to record a completed maintenance action. Select the entity type (vehicle, battery, controller, dock) and the specific item from the dropdown. Enter the maintenance type, description, who performed it, the date, and any notes. Maintenance records appear in the History section and on the specific equipment's detail page.

### 10.2 Scheduling Recurring Maintenance

The Schedules section at the bottom of the page manages recurring maintenance tasks. Click Add Schedule to create a monthly, quarterly, or yearly recurring task. Assign it to a specific piece of equipment or make it organization-wide. Optionally assign it to a specific pilot.

### 10.3 Completing Scheduled Tasks

When a scheduled task is due, it appears in the Upcoming section at the top of the page. Click the checkmark button to mark it complete. The system automatically creates a maintenance record and recalculates the next due date based on the schedule frequency.

---

## 11. Activity Reports

The Activity Reports page (formerly Incidents) tracks both problems and successes.

### 11.1 Reporting Incidents

Click Report and select "Incident" as the type. Choose a category (crash, near miss, equipment damage, injury, airspace violation, other), severity level, and link to the relevant flight, pilot, and vehicle. Describe the incident and any damage.

### 11.2 Recording Successes

Click Report and select "Success" as the type. Choose a category (missing person found, suspect located, evidence collected, community event, training success, other). Describe the outcome and its impact. Tracking successes helps demonstrate the value of the drone program to command staff and the community.

### 11.3 Resolution Workflow

Supervisors can update an incident's status from open to investigating to resolved to closed. Add a resolution description, corrective actions taken, and resolution date. Equipment can be grounded as part of an incident response.

---

## 12. Compliance Dashboard

The Compliance page provides a single view of your organization's regulatory and operational compliance.

### 12.1 Compliance Score

A score from 0 to 100 indicates overall compliance health, calculated from expired certifications, expired FAA registrations, overdue maintenance, and open incidents. Green (80+) indicates good standing, amber (60-80) indicates attention needed, red (below 60) indicates immediate action required.

### 12.2 Action Items

Cards show counts of items requiring attention: expired certifications, expiring certifications, expired registrations, overdue maintenance, open incidents, pending flight plans, and unreviewed flights. Each card links to the relevant page. A detailed table below lists all items sorted by urgency.

---

## 13. Analytics

### 13.1 Interactive Charts

The Analytics page displays charts for flights by purpose, flights by year, flights by pilot, monthly trends, average flight duration, and vehicle utilization hours.

### 13.2 Cross-Filtering

Click any element in any chart to filter all other charts. For example, click a pilot's name in the pie chart to see only that pilot's data highlighted across all charts. Click a year bar to filter to that year. Multiple filters can be combined. Active filters appear as pills at the top of the page. Click Clear Filters to reset.

### 13.3 Flight Locations Map

A map at the bottom of the Analytics page shows the takeoff location of every flight as a clickable marker. The map responds to active filters, showing only flights that match the current selection.

---

## 14. Reports

### 14.1 Generating Reports

Select a report type, date range, and optionally filter by specific pilots or vehicles. Click Generate to preview the report on screen.

### 14.2 Report Types

- **Flight Summary:** Total flights, hours, and a breakdown by purpose with a chart.
- **Pilot Hours:** Flight count, hours, and average duration per pilot.
- **Equipment Utilization:** Hours and flight count per vehicle.
- **Pilot Activity Summary:** Combined flight hours, mission hours, and training hours per pilot.
- **Annual Unit Report:** Year-over-year statistics with totals.
- **Pilot Certifications:** Certification status per pilot with expiration tracking.
- **Battery Status:** Battery inventory with cycle counts and health.
- **Maintenance History:** Maintenance records within a date range.

### 14.3 PDF Export

Click Download PDF to generate a professional PDF report including your organization name, logo, summary statistics, charts, and data tables.

### 14.4 CSV Export

Every page in the application has an Export CSV button that downloads the current data as a spreadsheet-compatible file.

---

## 15. Photo Gallery

### 15.1 Uploading Photos

Click Upload to add photos. You can select multiple files at once for batch upload. Add a title, description, date taken, and link one or more pilots in the photo.

### 15.2 Viewing and Navigating

Photos are displayed in a grid grouped by date. Click any photo to open the lightbox viewer. Use the left and right arrow keys (or on-screen buttons) to navigate between photos. Press Escape to close.

### 15.3 Linking Pilots

When uploading or editing a photo, select the pilots who appear in the photo. Their names are displayed on the photo card in the gallery and the photo appears on their pilot profile.

---

## 16. Document Storage

### 16.1 Folder Structure

The Document Storage page provides a folder-based file system. Default system folders (General, Certifications, Insurance, Maintenance, Reports) are created automatically. You can create additional folders and subfolders as needed.

### 16.2 Uploading Documents

Click Upload in the current folder to add a file. Enter a title and document type. Documents uploaded from other parts of the application (pilot profiles, certifications, vehicle pages) are automatically filed in the appropriate folder.

### 16.3 Moving and Renaming

Use the action buttons on each document to rename it, move it to a different folder, view it, or delete it.

---

## 17. Audit Log

### 17.1 Viewing Activity

The Audit Log (accessible to administrators only) shows a chronological record of every change made in the system: who did what, when, and what the old and new values were. This provides accountability and a complete audit trail.

### 17.2 Filtering and Exporting

Filter the audit log by entity type (flight, pilot, vehicle, etc.) or action type (create, update, delete). Click Export CSV to download the filtered log.

---

## 18. User Roles

### 18.1 Admin

Full access to everything. Can manage users, configure settings, access the audit log, manage API keys, and perform all actions in the system.

### 18.2 Supervisor

Can approve and deny flight plans. Can manage pilots, vehicles, certifications, and fleet equipment. Can resolve incidents and manage maintenance schedules. Cannot access user management, API configuration, or the audit log.

### 18.3 Pilot

Can add flights, mission logs, training logs, and maintenance records. Can complete checklists, submit flight plans, report incidents, and upload photos and documents. Can edit only their own pilot profile. Cannot manage other pilots, modify certifications, or access settings.

### 18.4 Viewer

Read-only access to all data. Can view dashboards, reports, flights, pilots, and all other pages. Cannot create, edit, or delete any records.

---

## 19. Mobile Access

### 19.1 Navigation

On mobile devices, the sidebar is replaced by a hamburger menu in the top-left corner. Tap the menu icon to open the sidebar as an overlay. The sidebar closes automatically when you navigate to a page.

### 19.2 Responsive Tables

Tables on mobile devices scroll horizontally. Less important columns are hidden on smaller screens to prioritize the most critical information. All data remains accessible by scrolling.

---

## 20. Backup and Recovery

### 20.1 Database Backup

The application stores all data in two SQLite database files and an uploads folder within the configured data directory. To create a backup:

1. Stop the container to ensure a clean backup.
2. Copy the `drone_unit_manager.db` file, the `telemetry.db` file, and the entire `uploads` directory to a safe location.
3. Restart the container.

For automated backups, schedule a cron job or use your hosting platform's backup tools to copy the data directory on a regular basis.

### 20.2 Restoring Data

1. Stop the container.
2. Replace the database files and uploads directory with your backup copies.
3. Start the container.

The application will use the restored data immediately. All user accounts, flights, certifications, and uploaded files will be restored to the state of the backup.
