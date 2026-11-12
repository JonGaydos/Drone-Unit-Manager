export const sections = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    topics: [
      {
        id: 'using-this-manual',
        title: 'Using this manual',
        summary: 'Use this manual to look up one thing at a time, or to read everything in order.',
        image: {
          src: '/manual/manual-layout-switch.png',
          alt: 'The Topics and One page switch at the top of the User Manual page',
          caption: 'The switch at the top of the manual chooses between Topics and One page.',
        },
        steps: [
          'Open **User Manual** in the sidebar.',
          'Choose **Topics** to see a menu of sections on the left (a bar at the top on a phone). Pick a topic and only that topic shows. Use the Previous and Next buttons at the bottom to read in order.',
          'Choose **One page** to see every section on one long page. Open a section to read it.',
          'Type in the box labeled **Search the manual...** to find a word. The menu narrows to the topics that contain it, and the first match opens.',
          'To share a topic, copy the address from your browser while the topic is open. Anyone who opens that address lands on the same topic.',
        ],
        notes: [
          'The manual remembers your choice of **Topics** or **One page** on each device.',
          'Opening a topic address always switches you to **Topics**.',
          'Every role sees every topic. Where something is limited to some roles, the topic says so in plain words. An admin can change those limits, so ask your admin if your app behaves differently.',
        ],
      },
      {
        id: 'first-run-setup',
        title: 'First-time setup',
        summary: 'The first time Drone Unit Manager starts, it asks you to set up your unit and create the first administrator. This happens once.',
        steps: [
          'Open the app address in your browser. The setup screen appears.',
          'On the **Organization** step, enter **Organization Name**, pick your **Time Zone**, enter **Your Name** and **Email Address**. Only your name is required. Then choose **Continue**.',
          'On the **Create Admin Account** step, choose a **Username** and a **Password**, and type the password again in **Confirm Password**.',
          'Enter the **Install Token** (see the notes below), then choose **Create Account & Start**.',
          'On the next screen, set up any of the optional items you want: **Organization Logo**, **Skydio Integration**, email sending, and **Initial Flight Log Import**. Each one is separate, so skip what you do not need.',
          'Choose **Go to Dashboard**.',
        ],
        notes: [
          'There is no default username or password. The account you create here becomes the administrator.',
          'A password needs at least 12 characters, one capital letter and one number.',
          'The install token is a long code that proves you control the server. Whoever installed the app can read it from a file named install_token.txt in the app data folder, or from the app startup log.',
          'The time zone you pick sets how every date and time is shown. You can change it later in **Settings**, on the **General** tab, in the **Organization** card.',
          'Everything on the optional screen can be done later from **Settings**.',
        ],
      },
      {
        id: 'restoring-a-backup-at-setup',
        title: 'Restoring a backup on a new install',
        summary: 'If you are moving to a new install and have a backup file from the old one, restore it from the setup screen instead of starting empty.',
        steps: [
          'On the setup screen, choose **Restore from a backup instead?**.',
          'Choose the backup file (a ZIP file) from the old install.',
          'Enter the **Install Token** (see First-time setup for where to find it).',
          'Choose **Restore Backup**. When it finishes, you are sent to the sign-in screen.',
        ],
        notes: [
          'A backup holds everything, including passwords and keys. Store backup files as carefully as you store passwords.',
          'If the restore would remove or change items under legal hold, the screen lists them. You must type RESTORE HELD ITEMS before it continues.',
          'If the backup was made before passwords were included, the setup screen shows **Reactivate Administrator** instead. Enter the username of an administrator from the restored data, a new password and the install token, then choose **Reactivate & Sign In**. After you sign in, reset the other users\' passwords and re-enter any saved keys and email passwords.',
        ],
      },
      {
        id: 'navigating-the-app',
        title: 'Finding your way around',
        summary: 'The sidebar on the left lists every page you are allowed to see. The title of the page you are on shows in the bar at the top.',
        steps: [
          'Choose a name in the sidebar to open that page. The sidebar groups pages under Overview, Flight Ops, Fleet & Crew, Compliance, Media & Reports and System.',
          'On a computer, use the arrow at the bottom of the sidebar to shrink it to icons or open it again.',
          'On a phone or tablet, tap the menu icon at the top left to open the sidebar, then tap a page. It closes by itself.',
          'Choose **User Manual** just above your name to open this manual.',
          'To sign out, choose the **Log out** icon next to your name at the bottom of the sidebar.',
        ],
        notes: [
          'You only see pages your role can view. If a page you expect is missing, ask an admin to check your role.',
          'A red number beside **Flights** counts flights that still need review. An amber number beside **Flight Plans** counts plans waiting for approval.',
          'Admins can reorder or hide sidebar items, and turn the group headings on or off, in **Settings**, on the **General** tab, in the **Sidebar Configuration** card. Choose **Save Sidebar Config** to keep the changes.',
        ],
      },
      {
        id: 'command-palette',
        title: 'Search and jump (Ctrl+K)',
        summary: 'Use the search box to jump to a page, or to find a pilot, vehicle or flight without browsing for it.',
        steps: [
          'Press Ctrl+K (Cmd+K on a Mac) anywhere in the app, or choose the search box at the top of the page.',
          'Type part of a page name, such as Flights or Settings, and press Enter to go there.',
          'Or type at least two letters of a name or number to search pilots, vehicles and flights. Each result has a tag that shows what kind of record it is.',
          'Use the up and down arrow keys to move through the results, then press Enter to open one.',
          'Press Escape to close the box.',
        ],
        notes: [
          'Use the **All**, **Pilots**, **Vehicles** and **Flights** buttons under the box to show one kind of record. Page matches always show.',
          'When the box is empty, your last few destinations appear under **Recent**.',
          'The search box and the theme button are in the top bar, which shows on a computer or a wide tablet. On a phone, use the sidebar to move around.',
          'Search only shows what your role can view.',
        ],
      },
      {
        id: 'themes',
        title: 'Themes',
        summary: 'A theme changes the colors of the whole app. Pick one that is easy on your eyes.',
        steps: [
          'Choose the palette button at the right of the top bar. It shows the name of your current theme.',
          'Choose a theme from the list. The app changes right away.',
        ],
        notes: [
          'There are 14 themes, including Dark, Light, Glass, High Contrast, Night Vision and Sandstone. Sandstone is what a new install starts with.',
          'Your choice is saved to your profile, so it follows you to other devices.',
          'The top bar, and so the theme button, shows on a computer or a wide tablet.',
        ],
      },
      {
        id: 'links-between-records',
        title: 'Links between records',
        summary: 'Names and numbers in the app are links. Choose one to jump straight to that item.',
        notes: [
          'Pilot names, vehicle names, battery serials, sensors, attachments and flight numbers open that item\'s detail page.',
          'A purpose (the reason for a flight, such as Training) opens the Flights page filtered to that purpose.',
          'Use your browser Back button to return to where you were.',
          'You can only open an item if your role can view that part of the app.',
        ],
      },
      {
        id: 'dates-and-times',
        title: 'Dates and times',
        summary: 'Every date and time in the app is shown in your unit\'s time zone, so everyone sees the same thing.',
        notes: [
          'An admin sets the time zone in **Settings**, on the **General** tab, in the **Organization** card (**Time Zone**).',
          'A flight belongs to the local day it took off. An evening flight stays on that day, even if it is already the next day in UTC (the world time standard).',
          'CSV files (spreadsheet files) that you export use the same local times. A date range on an export covers whole local days.',
          'The flight export also includes the UTC takeoff and landing times next to the local ones.',
        ],
      },
    ]
  },
  {
    id: 'account-access',
    title: 'Signing In and Your Account',
    topics: [
      {
        id: 'signing-in',
        title: 'Signing in',
        summary: 'Sign in with the username and password an admin gave you. Your account is created by an admin, not by you.',
        steps: [
          'Open the app address in your browser.',
          'Enter your **Username** and **Password**. Both are case-sensitive.',
          'Choose **Sign In**.',
        ],
        notes: [
          'If you do not have an account, ask an admin to add you.',
          'An account that an admin has disabled cannot sign in. The screen says "Invalid credentials", the same as for a wrong password.',
          'A session lasts up to 12 hours, then you sign in again.',
          'If you try more than five times in one minute from the same device, sign-in pauses for a short while. Wait a minute and try again.',
        ],
      },
      {
        id: 'login-lock',
        title: 'Locked out after wrong passwords',
        summary: 'If you enter the wrong password too many times, the app locks sign-in for a while. This protects accounts from people guessing passwords.',
        notes: [
          'Ten wrong passwords for one account within 15 minutes, from the same device or network address, lock that address out of that account. Other addresses can still sign in.',
          'Fifty wrong passwords for one account within 15 minutes, counted across all addresses, lock the account for everyone.',
          'While locked, the screen says "Too many failed attempts for this account. Try again later." Even the right password is refused until the lock ends.',
          'The lock ends by itself 15 minutes after the failed tries. There is nothing to reset and no admin step.',
          'A successful sign-in clears the count for the address you signed in from.',
          'Someone who only knows your username cannot lock you out from your own address.',
        ],
      },
      {
        id: 'sessions-and-idle-lock',
        title: 'Staying signed in, signing out and the idle lock',
        summary: 'The app signs you out when you stop using it, so a screen left open cannot be used by someone else.',
        notes: [
          'A session lasts up to 12 hours.',
          'The idle lock signs you out of that browser when you have not used it for a while. The default is 30 minutes. Activity in any open tab keeps every tab signed in.',
          'When the idle lock signs you out, the sign-in screen says so. Your other devices stay signed in.',
          'Admins can change the wait to anything from 30 minutes to 12 hours in **Settings**, on the **General** tab, in the **Organization** card (**Idle lock**). It applies to every role, and a browser picks it up the next time it is refreshed.',
          'Choosing **Log out** signs you out on every device you use, not only this one.',
          'Changing a password, changing a role or disabling an account also signs that person out everywhere.',
        ],
      },
      {
        id: 'profile-and-password',
        title: 'Your profile and password',
        summary: 'Keep your email up to date, and change your password when you need to.',
        steps: [
          'Open **Settings**. On the **General** tab, find the **My Profile** card.',
          'Change your **Email** and choose **Save Profile**.',
          'To change a password, an admin opens **Settings**, then the **Users** tab, then the **Change Password** card. Enter **Current Password**, **New Password** and **Confirm New Password**, and choose **Change Password**.',
        ],
        notes: [
          'A password needs at least 12 characters, one capital letter and one number.',
          'Only an admin can change a display name. Everyone can change their own email.',
          'If you are not an admin and forget your password, ask an admin. In **Settings**, on the **Users** tab, they choose the key icon (**Reset password**) beside your name, type a new password and choose **Set**.',
          'Changing or resetting a password signs that person out on every other device.',
        ],
      },
      {
        id: 'user-roles',
        title: 'Roles',
        summary: 'Every account has one of four roles: Admin, Supervisor, Pilot or Viewer. The role decides what you can change. These are the starting settings, and an admin can change them.',
        notes: [
          '**Viewer**: Sees every part of the app and can export CSV files. Never changes anything. Pilot email addresses and phone numbers are hidden.',
          '**Pilot**: Sees every part of the app and can add records, such as flights, flight plans, incidents and logs. Can edit only their own records. Cannot delete flights. Can complete checklists and maintenance tasks, check equipment in and out, update a vehicle\'s location and generate reports.',
          '**Supervisor**: Can edit most records, review flights, approve and deny flight plans, manage pilots, fleet, certifications and checklists, and generate reports.',
          '**Admin**: Everything. Only admins manage users, the permission settings, system settings, integrations, backups and API tokens.',
          'Only admins see the audit log and manage vehicle registrations by default.',
          'Nobody can approve or deny a flight plan they submitted themselves, whatever their role.',
        ],
      },
      {
        id: 'role-permissions',
        title: 'Changing what each role can do',
        summary: 'Admins decide what Supervisors, Pilots and Viewers can do, one setting at a time. Admins only.',
        steps: [
          'Open **Settings**, then the **Users** tab, and find the **Role Permissions** card.',
          'Find the setting you want. Settings are grouped by feature, such as Flights or Pilots, with a column for each role.',
          'Change a cell. It is Yes or No, or None, Own or All for records that have an owner.',
          'Choose **Save changes** at the bottom to apply, or **Discard** to drop your edits.',
          'To go back to the starting settings, choose **Reset to defaults**.',
        ],
        notes: [
          'On a phone, the table becomes one card per feature, with a **Role** menu at the top.',
          'Changes apply from each person\'s next action. Nobody is signed out.',
          'Turning a feature\'s View off hides its pages, lists, search results, exports and sidebar entry, and also switches off the settings that depend on it.',
          'Some cells are locked and greyed out. Admins are always on. Viewers can never change anything. A change setting stays off while its View is off.',
          'Nobody can approve or deny their own flight plan. A legal hold blocks edits and deletes. The last active admin cannot be demoted, disabled or deleted.',
          'These stay admin only and cannot be handed out: managing users, this permission screen, settings and integrations, backup and restore, API tokens, bulk imports, flight purposes and permanent purge.',
          'Your own password, theme and profile are always yours to use.',
        ],
      },
      {
        id: 'default-permissions',
        title: 'What each role can do by default',
        summary: 'A quick reference for the starting settings. Check the **Role Permissions** card to see what your unit uses now.',
        notes: [
          '**View**: Supervisor, Pilot and Viewer can view every feature. Only the audit log is closed to all of them.',
          '**Create**: Supervisors and Pilots can add flights, flight plans, incidents, logs, maintenance records and calendar events. Viewers cannot.',
          '**Edit**: Supervisors can edit all of these records, and also pilot profiles, documents and photos. Pilots can edit only their own. Viewers cannot.',
          '**Delete flights**: Supervisors only.',
          '**Supervisors and admins only**: reviewing flights and bulk actions, approving or denying flight plans, resolving and deleting incidents, maintenance schedules, fleet management, deleting checkouts, adding, deleting or merging pilots, certifications, checklist templates, restoring documents and legal hold, folders, alerts, operating authority, and sending the email digest to another address.',
          '**Pilots and supervisors**: completing maintenance tasks, updating a vehicle\'s location, checking equipment in and out, completing checklists, seeing pilot email and phone, and generating reports.',
          '**Admins only**: vehicle registrations management and the audit log.',
          'A flight added by hand always starts as **Needs Review**. If someone without review rights edits a reviewed flight, it goes back to the review queue. Only reviewed flights count toward pilot currency.',
        ],
      },
      {
        id: 'own-records',
        title: 'What "Own" means',
        summary: 'Where a setting says Own, you can change only records that belong to you. This is how Pilots can fix their own work without touching anyone else\'s.',
        notes: [
          '**Flight**: you are the flight\'s pilot, or you logged it.',
          '**Flight plan**: you submitted it.',
          '**Incident**: you reported it.',
          '**Mission or training log**: you created it, or you are on its roster.',
          '**Maintenance record**: you created it.',
          '**Calendar event**: you created it.',
          '**Pilot profile**: it is the pilot your login is linked to.',
          '**Photo**: you uploaded it.',
          '**Document**: you uploaded it, or it is on your own pilot record or certification.',
          'Records made before this rule existed have no recorded creator. Only a role with All can edit them.',
          'A pilot with Own on flights cannot hand a flight to a different pilot.',
          'Own depends on linking each login to its pilot. An admin does this in **Settings**, on the **Users** tab, by choosing the edit icon (**Edit user**) and picking **Link to Pilot**. A pilot login with no link shows a **No linked pilot** badge and cannot edit its own flights or profile.',
        ],
      },
    ]
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    topics: [
      {
        id: 'overview',
        title: 'Overview',
        summary: 'The dashboard is a snapshot hub of your drone program. A hero panel shows the compliance score and how many pilots are current; a weather tile shows the GO/CAUTION/NO-GO advisory for your default location; and 30-day stat tiles (flights, hours, active pilots, fleet size) show trends. Further tiles cover recent flights, currency risk, flights needing review, maintenance due, certification expirations, activity by month, drone locations, and top pilots and vehicles. Click any card to open its detail page.'
      },
      {
        id: 'recent-flights',
        title: 'Recent Flights',
        summary: 'The recent flights table shows the last 10 flights. Click a flight date to view its full detail page with telemetry, map, and equipment information.'
      },
      {
        id: 'certification-expirations',
        title: 'Certification Expirations',
        summary: 'Certifications expiring within 90 days are shown with color-coded badges: green (60+ days), amber (30-60 days), and red (under 30 days or expired).'
      },
    ]
  },
  {
    id: 'calendar',
    title: 'Calendar',
    topics: [
      {
        id: 'unit-calendar',
        title: 'Unit Calendar',
        summary: `The Calendar page aggregates everything dated in your program into a single FullCalendar view. It pulls in:

• **Flights**: A per-day count badge (e.g. "3 flights"); click it to open the Flights page.
• **Missions**: Entries from the Mission Log on their mission date.
• **Training**: Entries from the Training Log on their training date.
• **Maintenance due**: The next-due date of each recurring maintenance schedule.
• **Cert expirations**: Each pilot certification's expiration date, labeled with the pilot and certification name.
• **Events and leave**: Manual entries you add yourself (see below).

Each category has a colored checkbox above the calendar to show or hide that type. Clicking a flight, mission, training, maintenance, or certification item navigates to the relevant page.`
      },
      {
        id: 'views',
        title: 'Views',
        summary: 'Switch between Month, Week, and List views using the buttons in the top-right of the calendar. Use prev/next and Today to move through the date range; only items within the visible range are loaded.'
      },
      {
        id: 'adding-events-and-leave',
        title: 'Adding Events and Leave',
        summary: `Click "Add event / leave" to create a manual entry. Choose a category (Event or Leave), a title, a start date, an optional end date (for multi-day entries), and optional notes.

Users with the create permission (everyone except viewers by default) can add their own events and leave. You can edit or delete an entry you created; by default supervisors and admins can edit or delete any manual entry. The other aggregated items (flights, missions, training, maintenance, certifications) are read-only on the calendar and are managed from their own pages.`
      },
    ]
  },
  {
    id: 'flights',
    title: 'Flights',
    topics: [
      {
        id: 'viewing-flights',
        title: 'Viewing Flights',
        summary: 'The Flights page shows all recorded flights with filtering by date range, pilot, vehicle, purpose, and review status. Use the text search to find flights by pilot name, vehicle, purpose, location, case number, or flight ID. Search and column sorting cover every flight, not just the page on screen.'
      },
      {
        id: 'adding-flights-manually',
        title: 'Adding Flights Manually',
        summary: 'Click "Add Flight" to record a flight manually. Select the pilot, vehicle, date, duration, purpose, and optionally a takeoff address and case number. A flight added by hand always starts as Needs Review, whoever logs it.'
      },
      {
        id: 'reviewing-flights',
        title: 'Reviewing Flights',
        summary: 'Flights imported from the Skydio API arrive with "Needs Review" status. Users with the review permission (supervisors by default) can review individual flights via the inline edit button, or use "Approve Page" to mark the visible page of pending flights as reviewed. Selecting rows with the checkboxes also enables bulk actions (reassign pilot, set purpose, mark reviewed, delete), each shown with a confirmation summarizing exactly what will change. When a user without the review permission edits a reviewed flight, it returns to the review queue.'
      },
      {
        id: 'flight-detail',
        title: 'Flight Detail',
        summary: 'Click a flight ID to see the full detail page. If telemetry data was synced, you\'ll see an interactive map with the flight path and charts for altitude, speed, and battery level over time. The telemetry label reads "Telemetry ✓" when the flight path is stored, "Telemetry pending" while sync can still fetch it, and "No telemetry" when there is none to fetch. Flights entered by hand show no label.'
      },
    ]
  },
  {
    id: 'fleet',
    title: 'Fleet Management',
    topics: [
      {
        id: 'vehicles',
        title: 'Vehicles',
        summary: 'The Fleet page is organized into tabs: Vehicles, Batteries, Controllers, Docks, Sensors, Attachments, and Other equipment. A status filter switches between In service, Retired & damaged, and All. Click any item to view its detail page with flight history, maintenance records, and specifications.'
      },
      {
        id: 'batteries',
        title: 'Batteries',
        summary: 'Battery records track serial numbers, cycle counts, and health status. Battery assignments to flights are tracked automatically when imported from the API.'
      },
      {
        id: 'controllers',
        title: 'Controllers',
        summary: 'Remote controller inventory is tracked separately. Controllers can be assigned to specific vehicles or shared across the fleet.'
      },
      {
        id: 'components',
        title: 'Components',
        summary: 'Component-level tracking (propellers, gimbals, cameras) lets you monitor individual parts with flight hours, installation dates, and warranty information.'
      },
      {
        id: 'equipment-checkout',
        title: 'Equipment Checkout',
        summary: 'The equipment checkout system provides chain-of-custody tracking. Check equipment out to a pilot, and check it back in when returned.'
      },
      {
        id: 'equipment-dropdowns',
        title: 'Equipment Dropdowns',
        summary: 'When adding or editing a flight, equipment fields (battery, sensor package, attachments) show a dropdown of existing Fleet inventory. You can type to search or select from the list. Typing a new serial number automatically creates a Fleet record for it.'
      },
      {
        id: 'merging-duplicates',
        title: 'Merging Duplicates',
        summary: 'If duplicate equipment records exist (e.g., two entries for the same battery), use the merge button (icon) in Fleet > Batteries/Sensors/Attachments. Select the duplicate to absorb: all flight references will be updated and the duplicate deleted.'
      },
      {
        id: 'battery-health-tracking',
        title: 'Battery Health Tracking',
        summary: 'Each battery has a health history chart showing health percentage and cycle count over time. Go to Fleet > click a battery > Health History section. Use "Record Reading" to manually add health data points. Health readings are also recorded automatically during Skydio API sync.'
      },
    ]
  },
  {
    id: 'checkouts',
    title: 'Equipment Checkouts',
    topics: [
      {
        id: 'checking-equipment-out',
        title: 'Checking Equipment Out',
        summary: `The Equipment Checkouts page provides chain-of-custody tracking. Click "Check Out" and choose the equipment type (vehicle, battery, controller, dock, sensor, or attachment), the specific item, and the pilot who is taking it. You can optionally set an expected return date and notes.

The checkout defaults to the logged-in user as the holder, but you can pick any pilot (for example, a supervisor recording a checkout on someone's behalf). Equipment that is already checked out cannot be checked out again until it is returned.`
      },
      {
        id: 'checking-equipment-back-in',
        title: 'Checking Equipment Back In',
        summary: 'In the "Currently Out" list, click "Check In" on a row, confirm who returned the item, and add optional notes. The record is then marked returned with a timestamp. Both the user who entered the record and the pilot who held or returned the item are captured in the audit log.'
      },
      {
        id: 'active-and-returned-records',
        title: 'Active and Returned Records',
        summary: 'The page shows a "Currently Out" section with everything still checked out, and a History section. Toggle "Show returned" to include completed (returned) records in the History list. By default supervisors and admins can delete a checkout record.'
      },
    ]
  },
  {
    id: 'locations',
    title: 'Drone Locations',
    topics: [
      {
        id: 'last-known-location',
        title: 'Last-Known Location',
        summary: `The dashboard includes a Locations tile listing each active drone and its last-known location. A drone's location is the more recent of an active equipment checkout (shown as "with <pilot>") or a manually set location.`
      },
      {
        id: 'setting-a-location',
        title: 'Setting a Location',
        summary: `Use the "Set location…" dropdown on each drone in the dashboard Locations tile to set its location to either a named place or a specific pilot. Setting a location manually updates the last-known location immediately.

The list of named places (for example North, Central, South) is configured by admins in Settings under Drone Locations. Pilots are always available as location targets in addition to the configured places.`
      },
    ]
  },
  {
    id: 'logs',
    title: 'Mission Log & Training Log',
    topics: [
      {
        id: 'mission-log',
        title: 'Mission Log',
        summary: `The Mission Log records non-flight missions and operations. Each entry has a date, title, reason/purpose, location, case number, drone used, man-hours, optional start/end times, description, and notes. You can attach multiple pilots to a mission, each with a role (PIC, Observer, Spotter, Visual Observer, Support) and hours. By default pilots can add entries and edit or delete the ones they created or are rostered on, and supervisors can change any entry; use the search box and date/pilot filters to find missions, and Export CSV to download the list.`
      },
      {
        id: 'training-log',
        title: 'Training Log',
        summary: 'The Training Log records training events. Each entry has a date, training type (e.g. Recurrent), title, location, instructor, man-hours, optional start/end times, and a drone used. Like missions, training entries support multiple pilots with a role and hours each (the Student role is also available for training).'
      },
    ]
  },
  {
    id: 'pilots',
    title: 'Pilots',
    topics: [
      {
        id: 'pilot-profiles',
        title: 'Pilot Profiles',
        summary: 'Each pilot has a profile with contact information, badge number, photo, and status (active/inactive). Click a pilot\'s name to view their full profile with flight history, certifications, and training records. By default supervisors can edit any profile and pilots only their own; the Role Permissions grid can change this.'
      },
      {
        id: 'pilot-currency',
        title: 'Pilot Currency',
        summary: `Currency rules define how many flight hours (and optionally how many flights) a pilot must log within a rolling period to stay current (e.g., 5 hours in 90 days).

Admins create rules from Settings → General → Currency Rules. Changing rules needs the certifications manage permission, which supervisors hold by default, but the Settings page itself is admin-only. Rules can be scoped to a specific vehicle model or apply across all aircraft. Once at least one active rule exists, each pilot's detail page shows a Currency Status section with per-rule progress, current/lapsed badge, and the projected expiry date (the date the pilot would lapse if they don't fly again).

Only reviewed flights count toward currency, from every source. A flight that still needs review, including one sent back to the queue after an edit, does not count until a supervisor reviews it, so a pilot can show as lapsed while their flights wait for review.`
      },
      {
        id: 'needs-attention',
        title: 'Needs Attention',
        summary: `Each pilot's detail page has a Needs Attention card that aggregates the items most likely to require action for that pilot:

• **Lapsed currency**: Any active currency rule the pilot is not current on, shown in red.
• **Expired certifications**: Certifications past their expiration date, shown in red.
• **Expiring certifications**: Certifications expiring within 30 days, shown in amber with the days remaining.

When nothing is outstanding, the card shows an "All clear" message. The count of items appears in the card header.`
      },
    ]
  },
  {
    id: 'certifications',
    title: 'Certifications',
    topics: [
      {
        id: 'certification-types',
        title: 'Certification Types',
        summary: 'Create custom certification types from the Settings page (e.g., Part 107, TRUST, Night Waiver). Each type can have custom status labels and renewal periods.'
      },
      {
        id: 'tracking-expirations',
        title: 'Tracking Expirations',
        summary: 'The Certifications page shows a matrix of all pilots and their certification statuses. Color-coded badges indicate valid, expiring soon, or expired status. The system generates alerts for upcoming expirations.'
      },
    ]
  },
  {
    id: 'maintenance',
    title: 'Maintenance',
    topics: [
      {
        id: 'maintenance-records',
        title: 'Maintenance Records',
        summary: 'Record maintenance events for any vehicle, battery, controller, or dock, or pick "Other" for items not tied to equipment (e.g., an FAA authorization renewal). Include the date, description, technician, and notes. Use the paperclip on any history row to attach related documents.'
      },
      {
        id: 'schedules-tasks',
        title: 'Schedules & Tasks',
        summary: 'Set up recurring maintenance schedules (monthly, quarterly, yearly, every 2 or 3 years) or one-time tasks with a specific due date via Add Schedule / Task. The system tracks when each item is next due and generates alerts when overdue. Marking a one-time task complete logs a maintenance record and closes the task; recurring schedules roll forward to the next due date.'
      },
    ]
  },
  {
    id: 'weather',
    title: 'Weather',
    topics: [
      {
        id: 'weather-briefing',
        title: 'Weather Briefing',
        summary: 'The Weather page provides a live aviation weather briefing using METAR and TAF data. Enter a location (airport code, city, or GPS coordinates) to get current conditions.'
      },
      {
        id: 'default-location',
        title: 'Default Location',
        summary: 'On load, the Weather page pre-populates to your organization Default Location (set in Settings). If no Default Location is configured, it falls back to the White House in Washington D.C. so the page always has a sensible center. Your recently searched locations are remembered and shown as quick-pick buttons under Recent Locations.'
      },
      {
        id: 'go-no-go-advisory',
        title: 'GO/NO-GO Advisory',
        summary: 'Based on your configured weather thresholds (wind speed, visibility, cloud ceiling), the system provides a GO, CAUTION, or NO-GO advisory. Configure thresholds from the Settings page.'
      },
    ]
  },
  {
    id: 'airspace',
    title: 'Airspace (ADS-B)',
    topics: [
      {
        id: 'live-aircraft-map',
        title: 'Live Aircraft Map',
        summary: 'The Airspace page shows a live map of nearby manned aircraft using ADS-B data from adsb.lol. Click anywhere on the map to set your search center: a blue circle shows the search radius. Aircraft markers are color-coded by altitude: red (below 400ft, drone zone), orange (400-1000ft), yellow (1000-5000ft), blue (5000-15000ft), gray (above 15000ft).'
      },
      {
        id: 'using-the-map',
        title: 'Using the Map',
        summary: 'Click a location on the map to start scanning. Adjust the radius (25-200 miles) and refresh interval (5-30 seconds or off) using the controls at the top. Click any aircraft marker to see its callsign, altitude, speed, heading, squawk code, and aircraft type. The aircraft count and last refresh time are shown in the top bar.'
      },
      {
        id: 'default-location-and-recent-chip',
        title: 'Default Location and Recent Chip',
        summary: 'On load, the map centers on your organization Default Location (set in Settings), falling back to the White House if none is configured. After you click a point, a "Recent" chip appears in the control bar so you can jump straight back to your last selected location.'
      },
    ]
  },
  {
    id: 'flight-plans',
    title: 'Flight Plans & Checklists',
    topics: [
      {
        id: 'flight-plan-submission',
        title: 'Flight Plan Submission',
        summary: 'Pilots can submit flight plans for approval by a user with the approval permission (a supervisor by default). Nobody approves or denies a plan they submitted. Include the mission objective, location, date/time, equipment, and weather conditions. Edit (pencil) changes a pending or denied plan; editing a denied or approved plan returns it to pending review. An admin can Reopen a denied or cancelled plan, which puts it back in the review queue.'
      },
      {
        id: 'pre-flight-checklists',
        title: 'Pre-Flight Checklists',
        summary: 'Create custom pre-flight checklist templates from the Checklists page. Pilots complete checklists before each flight, and completed checklists are stored for compliance records. A checklist submitted with required items unticked is saved as not passed; the Submit button says so. A template that has been used cannot be deleted, because submitted checklists keep a link to it: edit it and untick Active to stop offering it. By default, supervisors can delete a submitted checklist entered by mistake from its detail view.'
      },
    ]
  },
  {
    id: 'documents',
    title: 'Documents & Photos',
    topics: [
      {
        id: 'document-storage',
        title: 'Document Storage',
        summary: 'Upload and organize documents in folders. Use the Upload button on the Documents page to add standalone files (FAA authorizations, forms, etc.) directly into the selected folder. System folders (General, Certifications, Insurance, Maintenance, Reports) are created automatically. Create custom folders for additional organization. Documents uploaded from pilot profiles and certifications are auto-filed.'
      },
      {
        id: 'deleting-recently-deleted-and-legal-hold',
        title: 'Deleting, Recently Deleted and Legal Hold',
        summary: `Deleting a document or photo moves it to Recently deleted rather than removing it. Users with the restore permission (supervisors by default) can restore it from there, and admins can delete it permanently. Deleting a folder moves its documents to Unfiled.

Users with the legal hold permission (supervisors by default) can place a document or photo on legal hold. A held item shows a lock and cannot be edited, deleted or permanently removed until the hold is released; a held document can still be moved to another folder. Viewing and downloading documents and photos is recorded in the audit log.`
      },
      {
        id: 'photo-gallery',
        title: 'Photo Gallery',
        summary: 'Upload photos from flights, training, and events. Photos are organized by date with a lightbox viewer. Associate pilots with photos for easy reference.'
      },
      {
        id: 'linking-photos-to-flights-and-incidents',
        title: 'Linking Photos to Flights and Incidents',
        summary: 'Flight and incident detail pages have a Photos section listing attached photos. Linking and unlinking photos (attaching existing gallery photos to a flight or incident, or detaching them) requires the restore and legal hold permission (files custody), which supervisors and admins hold by default. Pilots and viewers can see linked photos but cannot attach or detach them by default.'
      },
    ]
  },
  {
    id: 'reports',
    title: 'Reports & Analytics',
    topics: [
      {
        id: 'pdf-reports',
        title: 'PDF Reports',
        summary: `Generate professional PDF reports with your organization's logo and branding. Available report types:

• Flight Summary: All flights within a date range
• Pilot Hours: Flight hours by pilot
• Equipment Utilization: Usage statistics per vehicle
• Pilot Activity Summary: Per-pilot activity report
• Annual Unit Report: Yearly program summary
• Per-Pilot Annual Review: A yearly review per pilot; download as one combined PDF, or use "Download PDF Pack" for a ZIP with one PDF per pilot
• Certifications: Current certification status
• Battery Status: Battery health and usage
• Maintenance History: Maintenance records by date range

The report builder also has date-range presets, pilot and vehicle filters (shown only for reports that use them), an "Include non-unit flights" toggle, and a logo override.`
      },
      {
        id: 'csv-export',
        title: 'CSV Export',
        summary: 'Every list page supports CSV export. Click the "Export CSV" button to download the current view as a spreadsheet.'
      },
      {
        id: 'analytics',
        title: 'Analytics',
        summary: 'The Analytics page provides interactive Power BI-style charts. Click any chart element (a pilot, year, purpose, or vehicle) to cross-filter all other charts. The map shows all flight locations.'
      },
      {
        id: 'gpx-and-kml-export',
        title: 'GPX and KML Export',
        summary: 'Flight paths can be exported as GPX (for GPS devices) or KML (for Google Earth) from the flight detail page. These buttons appear when the flight has telemetry data. The exported files contain the full GPS track with altitude and speed data.'
      },
    ]
  },
  {
    id: 'compliance',
    title: 'Compliance',
    topics: [
      {
        id: 'compliance-score',
        title: 'Compliance Score',
        summary: 'The Compliance page calculates a 0-100 score based on certification status, registration status, maintenance compliance, pilot currency, and operating authority. Each category shows what\'s compliant and what needs attention.'
      },
      {
        id: 'operating-authority',
        title: 'Operating Authority',
        summary: `The Operating Authority page tracks the unit's own COAs and Part 107 waivers, with issue and expiry dates, a status badge, and attached documents. By default admins and supervisors can add and edit; pilots and viewers have read-only access.

An authority within 90 days of expiry takes 5 points off the compliance score. An expired authority marked "Expiry grounds the unit" caps the score at 50 no matter how clean everything else is, with the reason shown under the score, because a green score while the unit is unauthorised would be misleading. Untick that box for an authority whose lapse restricts one kind of operation rather than grounding the unit (a night waiver, for example); an expired one of those takes 10 points off instead.

Set a record's status to Superseded (renewed by a newer authority) or Not applicable (the unit no longer operates under it) to keep it on file for the reports without it counting against compliance. A unit with no authorities on file is scored exactly as before.

Authorities appear in the Annual Unit Report (those held during the reporting period) and in the Certifications report.`
      },
    ]
  },
  {
    id: 'incidents',
    title: 'Activity Reports (Incidents)',
    topics: [
      {
        id: 'incident-reporting',
        title: 'Incident Reporting',
        summary: 'Report incidents including crashes, near-misses, equipment failures, and successes (missing persons found, suspects located, evidence collected). Each report includes severity level, description, corrective actions, and can be linked to flights, pilots, and vehicles.'
      },
    ]
  },
  {
    id: 'integrations',
    title: 'Integrations & Import',
    topics: [
      {
        id: 'drone-provider-apis',
        title: 'Drone Provider APIs',
        summary: `The Integrations tab in Settings manages connections to drone manufacturer APIs. Skydio is fully supported; BRINC is shown as "Coming Soon". Each provider has credential fields, a Test Connection button, and three sync buttons:

• **Sync Now**: imports flights added since the last sync and refreshes the fleet (drones, batteries, controllers, sensor packages, attachments), plus telemetry for up to 10 flights. Your everyday sync.
• **Full Sync**: like Sync Now but ignores the last-sync date to re-check the recent flights the Skydio API returns (about 200), and deletes empty flights (no date or duration). Slower.
• **Sync Telemetry (10)**: fetches only the detailed flight path (GPS, altitude, speed) for the next 10 flights that need it. Press again to backfill more.

Note: the Skydio sync API only exposes recent flights (roughly the last 200), so neither Sync Now nor Full Sync can reach further back than that. To bring in older or complete history, use the flight-log import (Airdata, CSV, and the other supported formats) described below.

You can also set an Auto-Sync Interval (6, 12, or 24 hours) and a separate Telemetry Auto-Sync Interval (30 minutes to 6 hours) so syncs run automatically in the background.`
      },
      {
        id: 'skydio-cloud-api',
        title: 'Skydio Cloud API',
        summary: `To connect to the Skydio Cloud API:

1. Log into Skydio Cloud at cloud.skydio.com
2. Go to Settings > Integrations > API Tokens
3. Create a token with read access to: Flights, Flight Telemetry, Vehicles, Batteries, Controllers, Users, Attachments, Sensor Packages
4. In Drone Unit Manager, go to Settings > Integrations tab
5. Enter the API Token and Token ID
6. Click "Test Connection", then "Sync Now"

For automatic pilot matching, ensure each pilot's profile has their Skydio account email address.`
      },
      {
        id: 'sync-status-and-disconnect',
        title: 'Sync Status and Disconnect',
        summary: `Expanding the Skydio card shows a persistent sync-status block that updates after each sync without a page reload:

• **State**: Whether a sync is currently running (incremental, full, or telemetry) or idle.
• **Last synced**: When the last sync ran, as a relative time plus the exact timestamp.
• **Next sync**: The estimated time until the next scheduled auto-sync, when an auto-sync interval is set.
• **Last run**: A summary of the most recent run (new flights, vehicles, batteries, controllers, and error count) with a colored status dot: green for success, amber for a partial run, and red for a failure. If there were errors, the first one is shown with a "+N more" count.

The card also has a **Disconnect** button. Disconnecting clears the stored Skydio token so syncing stops; you can reconnect later by re-entering the token.`
      },
      {
        id: 'flight-log-import',
        title: 'Flight Log Import',
        summary: `Import flight data from multiple sources via Settings > Integrations tab:

• **Skydio CSV**: Flight records exported from Skydio Cloud. A row whose Flight ID is already in the app is skipped, except that its Battery value fills in that flight's battery serial when the flight has none. A filled battery does not change the flight's review status
• **Excel**: Spreadsheets with "Skydio" and "Pilot Info" sheets (up to 100,000 rows and 512 MB unpacked; a larger file is refused and nothing is imported)
• **DJI .txt**: DJI Go 4 flight log text files
• **Litchi CSV**: Litchi flight log exports
• **Airdata CSV**: Rich 52-column exports with gimbal, RC inputs, battery temperature, flight mode
• **Airdata JSON**: Single flight JSON exports from Airdata.com
• **Airdata ZIP**: Bulk export of all flights from Airdata.com (ZIP of JSON files)
• **Parrot / ANAFI**: GUTMA JSON flight logs
• **Flights CSV (exported from this app)**: The Flights page's Export CSV, read back in (for example onto another install). Pick this format by hand; rows already in the app are skipped

Format is auto-detected, or you can pick a specific format. Select multiple files at once using Ctrl+click or Shift+click. The app processes them sequentially with live progress tracking and automatic deduplication.`
      },
      {
        id: 'smtp-email',
        title: 'SMTP Email',
        summary: 'Configure SMTP settings in the Integrations tab to enable email digest notifications. Enter your SMTP host, port, username, password, from address, and TLS settings. Use the "Send Test Email" button to verify the configuration.'
      },
      {
        id: 'email-digest-notifications',
        title: 'Email Digest Notifications',
        summary: 'Once SMTP is configured, each user can set up email digest preferences in the Email Digest card on Settings > General. Turn digests on or off, choose daily or weekly (and the weekday), the hour to send at, and which categories to include: pending flight plan approvals, flights needing review, expiring certifications, expiring registrations, overdue maintenance, assigned missions, overdue equipment checkouts, and recent incidents. Roles allowed to redirect the digest can send it to another address. Preview shows what the next digest would hold, Send Test emails it now (a few times per 10 minutes), and the card lists recent sends. A test send does not stand in for the scheduled digest.'
      },
    ]
  },
  {
    id: 'settings',
    title: 'Settings & Admin',
    topics: [
      {
        id: 'settings-tabs',
        title: 'Settings Tabs',
        summary: 'The Settings page is organized into tabs: General (organization info, default location, weather thresholds, certification labels, mission purposes, drone locations, currency rules, sidebar config, backup and restore, automated backups), Users (change password, user management, role permissions), Integrations (provider APIs, SMTP, flight log import), and API Tokens (long-lived API keys for external access).'
      },
      {
        id: 'api-tokens',
        title: 'API Tokens',
        summary: `The API Tokens tab (admin only) issues long-lived keys for external tools that call the Drone Unit Manager API. When creating a token, choose a name, read-only or read & write access, an optional expiry (30 days, 90 days or 1 year; without one the token lasts until revoked), and a scope: either all areas or specific ones (Fleet, Flights, Pilots & Certifications, Maintenance, Operations, Documents & Media, Reports & Dashboard, Audit Log). The Audit Log area is never part of all areas and must be chosen explicitly. The token value is shown once, so copy it immediately. Existing tokens list their prefix, access, areas, and last-used time, and can be revoked. Settings, users, backups, and sync are never reachable with an API token.`
      },
      {
        id: 'organization-settings',
        title: 'Organization Settings',
        summary: 'Configure your organization name, logo, timezone, and idle lock from the Settings page. The idle lock (30 minutes by default, up to 12 hours) signs a browser out after that long with no input, for every role; a change reaches each browser at its next refresh or reload. Sessions still end after 12 hours. Signing out or locking in one tab signs out all open tabs.'
      },
      {
        id: 'default-location',
        title: 'Default Location',
        summary: 'The Default Location (General tab, admin only) sets the organization\'s map center. Type an address or place name and click Search to geocode it, then save it as the default. This location pre-populates the Weather page, the Airspace map, and the dashboard weather tile. If unset, the app falls back to the White House in Washington D.C.'
      },
      {
        id: 'sidebar-configuration',
        title: 'Sidebar Configuration',
        summary: `Admins can customize the left navigation from Settings (General tab):

• **Visibility**: Toggle the checkbox next to any item to show or hide it in the sidebar.
• **Reorder**: Drag items by the grip handle to reorder them, or use the up/down arrows for fine control.
• **Group headers**: Toggle whether section group headers (Overview, Flight Ops, etc.) are shown.

Click "Save Sidebar Config" to apply.`
      },
      {
        id: 'drone-locations',
        title: 'Drone Locations',
        summary: 'The Drone Locations list (General tab, admin only) defines the named places that appear in the dashboard Locations tile\'s "Set location" dropdown (for example North, Central, South). Add, edit, or remove places and save. Pilots are always selectable as locations in addition to these places.'
      },
      {
        id: 'user-management',
        title: 'User Management',
        summary: 'Admins can create, edit, and deactivate user accounts from Settings > Users. Assign roles and link users to pilot profiles. Only admins can change a display name; other users can change their own email address under My Profile on the General tab, and their theme from the palette icon in the top bar. What each role can do is set in the Role Permissions card below the user list.'
      },
      {
        id: 'audit-log',
        title: 'Audit Log',
        summary: `The Audit Log (admin only by default) shows a complete history of all actions taken in the system: who did what, when, and what changed. Use it for accountability and compliance auditing.

Every change to unit data is recorded automatically, including changes made by imports, syncs and scheduled jobs. Each entry shows the person's display name and login name, and the full list of fields that changed with old and new values. Bulk changes and background jobs appear as one summary entry with counts and record IDs, and name the person who started the job. Contact details such as email and phone numbers are hidden. Entries that came from a restored backup are marked Imported. Filters narrow the list by entity type, action, user and a From/To date range (days in the organization time zone). Export CSV downloads every entry matching the filters, including the login name, full changes and an Imported column.`
      },
    ]
  },
  {
    id: 'backup',
    title: 'Backup & Restore',
    topics: [
      {
        id: 'in-app-backup',
        title: 'In-App Backup',
        summary: `Admins can download a full backup from Settings → General → Backup & Restore. Click "Export Backup" to download a ZIP containing every table as JSON plus all uploaded files. The backup holds everything a restore needs, including password hashes, API tokens, and the SMTP password and Skydio token, with no encryption, so keep it as safe as the server itself. A checkbox controls whether flight telemetry (GPS, altitude, speed) is included; telemetry can be very large, so it is optional. The export is admin-only and recorded in the audit log.`
      },
      {
        id: 'automated-backups',
        title: 'Automated Backups',
        summary: 'Admins can also enable daily automated backups (Settings → General → Automated Backups). Set how many backups to keep and the hour of day to run. Backups are written under the data volume\'s backups folder; schedule changes take effect after the next app restart.'
      },
      {
        id: 'restoring-from-backup',
        title: 'Restoring From Backup',
        summary: `On a fresh install, open the setup screen, choose "Restore from a backup instead?", upload the backup ZIP, and enter the install token. The token is written to install_token.txt in the container's data directory (/app/data) and also printed to the container logs at first boot.

A restore brings back everything: data, files, settings, users with their passwords, API tokens, and the SMTP password and Skydio token. Everyone signs in again with their usual password, and the install token is retired.

Older backups, made before passwords were included, left them out. After restoring one of those, no one can sign in yet, so the setup screen reopens in recovery mode ("Restored backup detected"): enter the username of an administrator from the restored data, a new password, and the install token to reactivate that admin. The app then opens directly. Other restored users keep blank passwords until that admin resets them from Settings → Users, and API tokens, the SMTP password and the Skydio token need to be set again.

Audit entries from the backup are added to this install's own and marked Imported.

Restoring into an install that already has working logins is an operator task done against the backup API (POST /api/backup/import) with an admin token rather than through the app. It replaces all data, users, API tokens, settings and files and signs everyone out, so the API first refuses with 409 and changes nothing. To go ahead, send the call again with the form field confirm_restore set to the exact text REPLACE ALL DATA. If the backup would also remove or change a photo or document under legal hold, the API then refuses with a list of the held items; send the call again with confirm_holds set to the exact text RESTORE HELD ITEMS as well. Each held item that is removed or changed gets its own audit entry.`
      },
      {
        id: 'filesystem-backup-fallback',
        title: 'Filesystem Backup (Fallback)',
        summary: `If you prefer to snapshot the data directory directly, stop the container and copy these from the /app/data volume:

• drone_unit_manager.db (main database)
• telemetry.db (flight telemetry)
• uploads/ (documents and photos)

Restart the container when done. On startup the application runs any pending schema migrations automatically before serving.`
      },
    ]
  },
]
