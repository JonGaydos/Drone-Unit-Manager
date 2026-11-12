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
        title: 'What the dashboard shows',
        summary: 'The dashboard is the first page you see after you sign in. It gathers the numbers a unit checks every day: how compliant you are, what flew recently, and what needs attention. Click a card to open the page behind it.',
        image: {
          src: '/manual/dashboard-overview.png',
          alt: 'The dashboard with the compliance score at the top, four 30-day cards, recent flights and the attention cards',
          caption: 'The dashboard: compliance score, 30-day cards, recent flights and the lists that need attention.',
        },
        steps: [
          'Choose **Dashboard** in the sidebar, or sign in. It is the home page.',
          'Read the top panel for the compliance score and a one-line summary.',
          'Read the four cards under it for the last 30 days.',
          'Scan the lists below for anything late, lapsed or waiting for review.',
          'Click any card, row or link to open the full page.',
        ],
        notes: [
          'A card is empty when your role cannot see that kind of record. An admin can change this under **Settings**.',
          'Everything on the page is read-only, except the location list on the **Locations** card (see "Drone locations on the dashboard").',
        ],
      },
      {
        id: 'compliance-score',
        title: 'The compliance score',
        summary: 'The big number at the top is the unit\'s compliance score out of 100. It sums up how well pilots, certifications, maintenance and operating authorities are being kept up to date.',
        steps: [
          'Read the number. Green is 80 or more, amber is 60 to 79, red is below 60.',
          'Read the line beside it: pilots who are current, expired certifications, overdue maintenance and the state of your operating authorities.',
          'If a red line appears under the summary, it explains what is holding the score down.',
          'Choose **Open compliance dashboard** to see the detail.',
        ],
        notes: [
          'The score and the counts cover the whole unit. The names in the lists below them follow what your role may see.',
          'If no currency rules exist yet, the line says **(no currency rules)**. Set rules up so the count means something.',
        ],
      },
      {
        id: 'trend-cards',
        title: 'The 30-day cards',
        summary: 'Four cards compare the last 30 days with the 30 days before them, so you can see whether activity is rising or falling.',
        steps: [
          'Find **Flights (30d)**, **Hours (30d)**, **Pilots Flying (30d)** and **Vehicles Flown (30d)**.',
          'Read the big number: the total for the last 30 days.',
          'Read the small arrow and percentage: green and up means more than the 30 days before, amber and down means less, **flat** means about the same.',
          'Read the line beside it for the all-time total, the active pilots or the fleet size.',
          'Click a card to open Flights, Analytics, Pilots or Fleet.',
        ],
        notes: [
          'No arrow appears when the earlier 30 days had no activity, because there is nothing to compare with.',
        ],
      },
      {
        id: 'attention-cards',
        title: 'Cards that need attention',
        summary: 'Four cards point at work that is late or about to be. Check them at the start of each shift.',
        steps: [
          '**Currency Risk** lists up to five pilots whose currency has lapsed or ends within 30 days, and shows how many are lapsed. A red **LAPSED** badge means they are not current now. A day count means days left. Click a name to open the pilot.',
          '**Needs Review** shows how many flights are waiting for a supervisor. Choose **Open** to see them in Flights. When none are waiting it says **Queue is clear**.',
          '**Maintenance Due** lists the most overdue items first. Red means overdue, amber means due within 7 days. Click one to open Maintenance.',
          '**Cert Expirations** lists certifications that end within 90 days, soonest first. Amber means 30 days or less. Click one to open the pilot.',
        ],
        notes: [
          'If your unit has no currency rules, **Currency Risk** says **No rules defined** and links to **Set up rules**.',
          'A certification that is already expired is not on **Cert Expirations**. It is counted in the top panel instead.',
        ],
      },
      {
        id: 'activity-and-top-lists',
        title: 'Recent flights, activity and top lists',
        summary: 'These cards show what the unit has been flying: the latest flights, a chart by month, and who and what flew the most in the last 30 days.',
        steps: [
          '**Recent Flights** shows the latest ten. Each row has the flight number or short code, the pilot, the drone, the purpose and the duration. Click a row to open the flight. Choose **All** to see every flight.',
          '**Activity by Month** is a bar chart of flights for up to the last 12 months. Hover a bar for its count. Choose **Analytics** for the full charts.',
          '**Top Pilots (30d)** and **Top Vehicles (30d)** rank by flight hours. Click a name to open that pilot or vehicle.',
        ],
      },
      {
        id: 'drone-locations',
        title: 'Drone locations on the dashboard',
        summary: 'The **Locations** card tells you where each drone is right now, for example at a station or with a pilot. You can update it from here when a drone moves.',
        steps: [
          'Find the drone on the **Locations** card.',
          'Open the **Set location…** list beside it.',
          'Choose a place under **Places**, or a pilot under **Pilots**.',
          'The card updates at once.',
        ],
        notes: [
          'Supervisors, pilots and admins can change a location by default. Viewers see the card but not the list.',
          'The list of places is set by an admin in **Settings**. If it was never changed, the places are North, Central and South.',
        ],
      },
    ]
  },
  {
    id: 'analytics',
    title: 'Analytics',
    topics: [
      {
        id: 'reading-the-charts',
        title: 'Reading the charts',
        summary: 'Analytics turns your flight history into charts. Use it to see when, why and by whom your drones fly, and how that has changed over the years.',
        steps: [
          'Choose **Analytics** in the sidebar.',
          '**All Time Flights by Purpose** and **Flights Per Year** are bar charts of flight counts.',
          '**Flights by Pilot** is a ring chart. Each pilot has a color and a name in the list beside it.',
          '**Average Flight Duration by Year** is a bar chart. Hover a bar to see the average in seconds.',
          '**Monthly Flight Trends** is a line chart of flights per month.',
          '**Top Vehicles by Flight Hours** shows the drones that flew the most.',
          '**Pilot Hours Leaderboard** is a table of hours and flights for each pilot.',
        ],
        notes: [
          'A **Flight Locations** map appears at the bottom only when some flights have a recorded take-off point.',
          'You need permission to view flights to open Analytics. The vehicle chart also needs permission to view the fleet. Both are on by default for every role.',
        ],
      },
      {
        id: 'filtering',
        title: 'Filtering by clicking',
        summary: 'Click part of one chart and every other chart narrows to match. For example, click one pilot to see only their purposes, years and hours.',
        image: {
          src: '/manual/analytics-filtering.png',
          alt: 'The Analytics page with one pilot selected and the active filter shown above the charts',
          caption: 'With a pilot selected, the Active filters bar appears and the other charts show only that pilot.',
        },
        steps: [
          'Click a bar in **All Time Flights by Purpose** to filter by purpose.',
          'Click a bar in **Flights Per Year** or **Average Flight Duration by Year** to filter by year.',
          'Click a slice of **Flights by Pilot**, a name beside it, or a row in the leaderboard to filter by pilot.',
          'Look at the **Active filters:** bar at the top. It shows each filter you have set.',
          'Click a chip in that bar to remove one filter, or choose **Clear Filters** to remove them all.',
        ],
        notes: [
          'You can combine one pilot, one year and one purpose.',
          'Faded bars show the full total. Solid bars show the part that matches your filters. In the leaderboard, the number in brackets is the filtered figure.',
          'Clicking the selected item again removes that filter.',
          'The vehicle chart and the monthly line change with your filters, but you cannot click them to filter.',
        ],
      },
    ]
  },
  {
    id: 'calendar',
    title: 'Calendar',
    topics: [
      {
        id: 'unit-calendar',
        title: 'The unit calendar',
        summary: 'The calendar shows everything with a date in one place: flights, missions, training, maintenance due dates, certification expiry dates, and events and leave you add yourself.',
        steps: [
          'Choose **Calendar** in the sidebar.',
          'Use the checkboxes **Flights**, **Missions**, **Training**, **Maintenance due**, **Cert expirations**, **Events** and **Leave** above the calendar to show or hide each kind. Each has its own color.',
          'Use **prev**, **next** and **today** to move through time.',
          'Switch the view with **month**, **week** or **list**.',
          'Click an item to open the page behind it.',
        ],
        notes: [
          'Flights show as one badge per day, such as 3 flights. Click it to open Flights.',
          'Only the dates you are looking at are loaded, so moving to a new month can take a moment.',
          'Missions, training, maintenance and certifications are read-only here. Change them on their own pages.',
          'Everyone can see the calendar by default.',
        ],
      },
      {
        id: 'adding-events',
        title: 'Adding events and leave',
        summary: 'Add your own entries for things that are not flights, such as a team briefing, a range day or time off. Everyone who can see the calendar sees them.',
        image: {
          src: '/manual/calendar-adding-events.png',
          alt: 'The Add event / leave dialog with title, category, dates and notes',
          caption: 'The Add event / leave dialog.',
        },
        steps: [
          'Choose **Add event / leave** at the top right.',
          'Type a **Title**.',
          'Pick a **Category**: **Event** or **Leave**.',
          'Pick the **Start date**. For more than one day, also pick an **End date (optional)**. It cannot be before the start date.',
          'Add **Notes (optional)** if you want.',
          'Choose **Save**.',
        ],
        notes: [
          'Supervisors and pilots can add entries by default. Viewers cannot, and do not see the button.',
        ],
      },
      {
        id: 'editing-events',
        title: 'Changing or deleting an entry',
        summary: 'Open an event or leave entry to correct it or remove it.',
        steps: [
          'Click the entry on the calendar. The **Edit entry** dialog opens.',
          'Change the fields and choose **Save**, or choose **Delete** and confirm to remove it.',
        ],
        notes: [
          'Supervisors and admins can change any entry by default. Pilots can change only their own.',
          'If you may not change an entry, the dialog still opens so you can read it, but **Save** is greyed out and there is no **Delete**.',
          'An admin can change who may edit under **Settings**.',
        ],
      },
    ]
  },
  {
    id: 'flights',
    title: 'Flights',
    topics: [
      {
        id: 'viewing-flights',
        title: 'Finding and filtering flights',
        summary: 'The **Flights** page lists every recorded flight. Use the filters and the search box to narrow the list, and the column headings to sort it.',
        image: {
          src: '/manual/flights-viewing-flights.png',
          alt: 'The filter bar on the Flights page with Date From, Date To, Pilot, Vehicle and Purpose',
          caption: 'The filters above the flights list.',
        },
        steps: [
          'Choose **Flights** in the sidebar.',
          'Choose **All**, **Needs Review** or **Reviewed** at the top. The number beside **Needs Review** counts every flight waiting for review, not only the ones on screen.',
          'Set **Date From** and **Date To** to show a range of dates.',
          'Pick a **Pilot**, a **Vehicle** or a **Purpose**. Under **Purpose**, **No Purpose** shows flights that have none.',
          'Type in **Search flights...** to find a word in the pilot, vehicle, purpose, location, case number or flight ID.',
          'Click a column heading (**Date**, **Pilot**, **Vehicle**, **Purpose**, **Duration** or **Status**) to sort. Click it again to reverse the order.',
          'Use **Previous** and **Next** at the bottom to move between pages.',
        ],
        notes: [
          'Each page holds 100 flights. The line at the bottom, such as "Showing 1-100 of 250 flights", tells you where you are.',
          'Filters, search and sorting cover every flight, not only the page on screen. Changing one takes you back to page 1.',
          'The **Vehicle**, **Purpose** and **Location** columns are hidden on a narrow screen. Open the flight to see them.',
          'Click a flight ID to open the flight, a pilot name to open the pilot, or a vehicle name to open the vehicle.',
          'The small line under the status reads "Telemetry ✓" when the flight path is stored, "Telemetry pending" while it can still be fetched, and "No telemetry" when there is none to fetch. Flights you enter by hand show nothing there. Telemetry means the recorded track of the flight: position, height, speed and battery.',
          'Everyone can see flights by default, including viewers.',
        ],
      },
      {
        id: 'adding-flights-manually',
        title: 'Adding a flight by hand',
        summary: 'Use this to record a flight that did not come in from a drone provider, such as a flight you flew with an aircraft that is not connected.',
        image: {
          src: '/manual/flights-adding-flights-manually.png',
          alt: 'The Add Flight dialog with pilot, vehicle, date, duration, purpose, times, addresses and equipment fields',
          caption: 'The Add Flight dialog.',
        },
        steps: [
          'On **Flights**, choose **Add Flight**.',
          'Pick the **Pilot** and the **Vehicle**. If the vehicle has a problem (overdue maintenance, an expired registration or a status other than active), a box called **Pre-flight warnings for this vehicle** appears. The warnings do not stop you from saving.',
          'Enter the **Date** and the **Duration (seconds)**. Or enter the **Takeoff Time** and **Landing Time** and leave **Date** and **Duration (seconds)** empty, and the app works them out.',
          'Pick a **Purpose**.',
          'Fill in anything else you know: **Takeoff Address**, **Landing Address**, the latitude and longitude boxes, **Distance (m)**, **Operating Cost ($)**, **Case Number**, **Battery**, **Sensor Package**, the four **Attachment** boxes, **Carrier(s)** and **Notes**.',
          'Choose **Add Flight**.',
        ],
        notes: [
          'The date and times in the form are in your unit\'s time zone.',
          '**Landing Time** must be after **Takeoff Time**, or the flight is not saved.',
          'If you fill in **Date** or **Duration (seconds)** as well as the times, they must agree. The date must be the takeoff date, and the duration must match the time between takeoff and landing to within a minute. Otherwise the app refuses to save. Leave them empty to avoid this.',
          'A flight you add by hand always starts as **Needs Review**, whoever adds it.',
          'To log a flight that is much like an earlier one, choose the copy icon (**Duplicate**) at the end of that row. The pilot, vehicle, purpose, takeoff address and equipment are filled in. The date, times and duration are left empty.',
          'Supervisors and pilots can add flights by default. Viewers cannot, and do not see the button. An admin can change this under **Settings**.',
        ],
      },
      {
        id: 'reviewing-flights',
        title: 'Reviewing flights',
        summary: 'Flights that come in from a drone provider, and flights added by hand, wait as **Needs Review** until someone checks them. Reviewing means checking the pilot, purpose and details are right and marking the flight **Reviewed**.',
        image: {
          src: '/manual/flights-reviewing-flights.png',
          alt: 'The bar that appears when flights are selected, with Reassign pilot, Set purpose, Mark reviewed, Delete and Clear',
          caption: 'The bar for working on several selected flights at once.',
        },
        steps: [
          'To review one flight, click the **Needs Review** badge in its row. It turns to **Reviewed**. Click it again to send it back.',
          'To fix details at the same time, choose the pencil icon (**Edit**) at the end of the row. Change the **Date**, pilot, **Purpose** or **Duration** and choose the check mark to save, or the X to cancel.',
          'To review everything on the page, choose **Approve Page** (it shows how many flights it covers) and confirm.',
          'To change several flights, tick their boxes (the box in the heading selects the whole page). A bar shows how many are selected.',
          'In that bar, pick **Reassign pilot…** or **Set purpose…**, or choose **Mark reviewed**. A message shows exactly what will change. Confirm to go ahead.',
          'To remove flights, choose **Delete** in the bar, or the trash icon on one row, and confirm.',
        ],
        notes: [
          'Reviewing, **Approve Page** and the selection boxes are for supervisors and admins by default.',
          '**Reassign pilot…** and **Set purpose…** also need permission to edit every flight, which supervisors have. **Delete** needs permission to delete any flight. Pilots cannot delete flights by default.',
          'Pilots can edit only their own flights by default. That means flights flown by their own pilot record, or logged by them. They cannot change the pilot on a flight.',
          'If someone who cannot review changes a flight that is already **Reviewed**, it goes back to **Needs Review**.',
          'Deleting a flight also removes its telemetry. It cannot be undone.',
          'The number beside **Flights** in the sidebar shows how many flights wait for review.',
          'An admin can change who may review, edit and delete under **Settings**.',
        ],
      },
      {
        id: 'flight-detail',
        title: 'The flight page',
        summary: 'Click a flight ID to open everything recorded about one flight: who flew it, what with, when and where, the telemetry charts and the flight path on a map.',
        steps: [
          'Click the flight ID in the **Flights** list.',
          'Read the details in the card. The badges at the top show the review status, the telemetry label and where the flight came from.',
          'If there is a recorded track, scroll down to see the **Flight Path** map and the charts **Altitude (ft)**, **Speed (mph)** and **Battery (%)**. Move the mouse over a chart to read exact values.',
          'To change the flight, choose **Edit**, change the fields and choose **Save**. Choose **Cancel** to drop your changes.',
          'To mark it checked, choose **Approve Flight**.',
          'Choose **Back to Flights** to return to the list.',
        ],
        notes: [
          'With no recorded track, a flight that has takeoff coordinates shows a **Flight Location** map instead, and a note says there is no telemetry.',
          'A flight with a recorded track also has **GPX** and **KML** buttons. They download the flight path for other mapping programs (KML opens in Google Earth). They need permission to export, which everyone has by default.',
          '**Approve Flight** shows only on a flight that needs review, for people who can review and edit it.',
          '**Refresh from API** is for admins. It asks the drone provider again for the latest data and track of this flight. It is greyed out when the aircraft has no connected provider account.',
          'In edit mode, people who can review also get a **Status** box and a **Unit totals** box. Untick **Counts** for a flight that should not count in your unit\'s totals, such as a vendor demo. A flight left out shows a **Not counted** badge.',
          '**Max Altitude** and **Max Speed** come from the recorded track and cannot be edited.',
          'The **Photos** card at the bottom lists photos linked to the flight. **Attach photos** adds photos from the Media page. Supervisors and admins can attach and detach by default.',
          'Pilots can edit only their own flights by default, so **Edit** may be missing on others.',
        ],
      },
      {
        id: 'exporting-flights',
        title: 'Exporting and importing flights as CSV',
        summary: 'A CSV file is a plain table you can open in a spreadsheet. Export the flights you are looking at, or read an exported file back in, for example onto another install.',
        steps: [
          'On **Flights**, set the filters and search so the list shows the flights you want.',
          'Choose **Export CSV**. A file with those flights downloads.',
          'To read an exported file back in, an admin opens **Settings**, then the **Integrations** tab, and finds **Flight Log Import**.',
          'Choose the file, set **Format** to **Flights CSV (exported from this app)**, and choose **Import**.',
        ],
        notes: [
          'The file holds every flight the filters select, on every page, not only the page on screen.',
          '**Export CSV** shows for people allowed to export, which is everyone by default.',
          'Choose the **Flights CSV (exported from this app)** format by hand. Flights that are already in the app are skipped.',
          'Only admins can import. Other flight log formats (Skydio, DJI, Litchi, Airdata and more) are covered under **Integrations**.',
        ],
      },
    ]
  },
  {
    id: 'fleet',
    title: 'Fleet Management',
    topics: [
      {
        id: 'fleet-list',
        title: 'The Fleet page',
        summary: 'Use the Fleet page to see every piece of equipment your unit owns, one tab per kind, and to add, edit or retire it.',
        image: {
          src: '/manual/fleet-fleet-list.png',
          alt: 'The Fleet page on the Vehicles tab with the tab bar, search box, status filter, Export CSV and Add Vehicle buttons, and a table of vehicles with their FAA registration due dates',
          caption: 'The Fleet page on the Vehicles tab, narrowed to the demo vehicles with the search box.',
        },
        steps: [
          'Choose **Fleet** in the sidebar.',
          'Pick a tab: **Vehicles**, **Batteries**, **Controllers**, **Docks**, **Sensors**, **Attachments** or **Other**.',
          'Type in the search box to narrow the list. It searches every column of the table.',
          'Click a column heading to sort by it. Click it again to reverse the order.',
          'Click a name to open that item\'s own page.',
        ],
        notes: [
          'The list opens on **In service**. That hides equipment that is **Retired** or **Damaged**. Use the status list to switch to **Retired & damaged** or **All statuses**. A small "N hidden" note tells you how many items the filter is holding back.',
          'The status filter stays the same when you move between tabs.',
          'On the **Vehicles** tab, **FAA Reg** shows the current registration number and **Next Due** shows the days left before it expires. It reads **Overdue** once the date has passed. See **FAA registrations on a vehicle** for how the current registration is chosen.',
          '**Export CSV** saves the tab as a CSV file (a plain spreadsheet file you can open in Excel). Admins, supervisors, pilots and viewers can all export by default.',
          'Everyone who can view the fleet sees the lists. The **Add** button and the edit, merge and retire icons show only to people who can manage the fleet: admins and supervisors by default. An admin can change this under **Settings**.',
          'You can also open a tab directly with an address such as /fleet?tab=batteries.',
        ],
      },
      {
        id: 'adding-a-vehicle',
        title: 'Adding and editing a vehicle',
        summary: 'Use this when you buy or are issued a new aircraft, or when a detail of an existing one changes. The other tabs work the same way, with their own fields.',
        image: {
          src: '/manual/fleet-adding-a-vehicle.png',
          alt: 'The Add Vehicle dialog with serial number, manufacturer, model, nickname, acquired date and status filled in',
          caption: 'The Add Vehicle dialog.',
        },
        steps: [
          'On **Fleet**, open the **Vehicles** tab and choose **Add Vehicle**.',
          'Fill in **Serial Number**, **Manufacturer** and **Model**. A star marks the boxes you must fill in.',
          'Add a **Nickname** if you want one. The nickname is what shows in lists and menus.',
          'Optional: **API Serial**, **Acquired Date**, **Decommissioned Date**, **Status** and **Notes**.',
          'Choose **Add Vehicle**.',
          'To change a vehicle later, choose the pencil icon on its row in the list, change the boxes and choose **Update**. You can also edit on the vehicle\'s own page (see **The vehicle page**).',
        ],
        notes: [
          'Two vehicles cannot share a **Serial Number**. The app refuses a duplicate.',
          '**API Serial** (the full label is "API Serial (what the provider calls this aircraft)") is the serial number your drone provider, such as Skydio, uses for this aircraft. Fill it in only if it differs from your own serial number. A provider sync uses it to match the right aircraft.',
          'The **Status** choices for a vehicle are **Active**, **Maintenance**, **Retired** and **Damaged**. Setting **Retired** or **Damaged** fills in **Decommissioned Date** with today if you left it empty. It also ends the vehicle\'s maintenance schedules, so they stop showing as overdue.',
          '**Decommissioned Date** cannot be earlier than **Acquired Date**.',
          'An optional box that you empty in an edit is cleared on the record. The required boxes (**Serial Number**, **Manufacturer**, **Model**) cannot be left empty.',
          'The FAA registration is not part of this form. Add it on the vehicle\'s page, in the **FAA Registration** card.',
        ],
      },
      {
        id: 'vehicle-page',
        title: 'The vehicle page',
        summary: 'Open a vehicle to see its flight history, equipment, registration, components and documents in one place.',
        steps: [
          'On **Fleet**, click a vehicle\'s name.',
          'The top shows the photo, the name, the serial number, the **API** serial, the **FAA** registration text, the acquired date and the status.',
          'Four cards show **Total Flights**, **Total Hours**, **Last Flight** and **Active Batteries**.',
          '**Equipment History** has four tabs: **Batteries**, **Controllers**, **Sensors** and **Mounted Accessories**.',
          '**Flight History** lists the vehicle\'s 50 most recent flights. Click a date to open the flight, or a name to open the pilot.',
          'Further down are the **FAA Registration** card, the **Components** card and **Documents**.',
          'To change the details, choose the pencil icon beside the name. Change the boxes, then choose **Save** (or **Cancel**).',
        ],
        notes: [
          '**Total Flights**, **Total Hours** and **Last Flight** count only flights that count toward your unit\'s totals. A flight marked **Not counted**, or one flown by a pilot who does not count toward unit totals (for example a vendor or guest operator), is left out. The flight list still shows it.',
          'The flight totals and **Flight History** show only to people who can view flights.',
          '**Active Batteries** counts the batteries whose **Vehicle Model** matches this vehicle\'s model and that are not retired.',
          'The **Batteries** tab under **Equipment History** lists the batteries that appear in this vehicle\'s recent flights. The **Controllers**, **Sensors** and **Mounted Accessories** tabs list your fleet\'s equipment of that kind. They are not limited to this vehicle.',
          'Admins can change the photo. Choose the small camera button on the photo\'s corner. You can use JPG, JPEG, PNG, GIF or WEBP pictures up to 50 MB. A file that is the wrong type, too large or not a real picture is refused, and the photo already there stays.',
          'Anyone who can manage the fleet can edit the vehicle. By default that is admins and supervisors.',
        ],
      },
      {
        id: 'retiring-and-deleting',
        title: 'Retiring and deleting equipment',
        summary: 'Use this when equipment leaves service. A vehicle is retired, so its flight history stays. Other equipment is deleted for good.',
        steps: [
          'On **Fleet**, find the item and choose the trash icon on its row.',
          'On the **Vehicles** tab the icon is called **Retire**. Confirm with **Retire**. The vehicle stays on record with its flights, marked **Retired**.',
          'On the other tabs the icon is called **Delete**. Confirm the question to delete the item.',
          'To bring a retired vehicle back, switch the status list to **Retired & damaged**, edit the vehicle and set **Status** back to **Active**.',
        ],
        notes: [
          'A deleted battery, controller, dock, sensor, attachment or other item cannot be brought back. Setting its **Status** to **Retired** instead keeps its history and hides it from the default list.',
          'Deleting a battery also deletes its health readings.',
          'Retired and damaged equipment cannot be checked out.',
          'Admins and supervisors can retire and delete by default.',
        ],
      },
      {
        id: 'batteries',
        title: 'Batteries',
        summary: 'Each battery has a record with its serial number, cycle count, health and the flights it has flown.',
        steps: [
          'On **Fleet**, open the **Batteries** tab and choose **Add Battery**.',
          'Fill in **Serial Number**. Optional: **Nickname**, **Manufacturer**, **Model**, **Vehicle Model**, **Cycle Count**, **Health %**, the two dates and **Status**.',
          'Choose **Add Battery**.',
          'To see more, click the battery\'s name. Its page shows **Cycle Count**, **Health**, **Total Flights**, **Total Hours**, its **Flight History**, the pilots who used it, its **Maintenance History** and **Documents**.',
          'To change it, choose the pencil icon on its row in the list, or the pencil on its own page.',
        ],
        notes: [
          '**Vehicle Model** says which aircraft model the battery fits. Pick one from the list or type a new one.',
          'The **Status** choices for a battery are **Active**, **Charging**, **Maintenance**, **Retired** and **Damaged**.',
          'A battery\'s flights are matched by its serial number. When a flight gets a battery serial the fleet does not know yet, the app adds a record for it.',
          '**Health %** must be between 0 and 100. Emptying the box clears the health, so the battery shows no health figure instead of 0%.',
          'The battery\'s flight and hour totals count only flights that count toward your unit\'s totals.',
        ],
      },
      {
        id: 'battery-readings',
        title: 'Battery health readings',
        summary: 'A reading is a measurement of a battery on one day. Record readings now and then, and the battery\'s Health History shows how it ages.',
        image: {
          src: '/manual/fleet-battery-readings.png',
          alt: 'The Record Battery Health Reading dialog with health percent, cycle count, voltage and notes filled in',
          caption: 'The Record Battery Health Reading dialog.',
        },
        steps: [
          'On **Fleet**, open the **Batteries** tab and click the battery\'s name.',
          'In the **Health History** card, choose **Record Reading**.',
          'Enter at least one of **Health %**, **Cycle Count** or **Voltage**. Add **Notes** if you like.',
          'Choose **Save Reading**.',
          'The chart shows health and cycle count over time. It stays empty until the battery has a reading.',
        ],
        notes: [
          'A saved reading also updates the battery\'s current **Health** and **Cycle Count** when you filled them in.',
          '**Cycle Count** cannot be lower than the battery\'s current count. Cycles only go up, so a lower number is refused as a likely typing mistake.',
          '**Health %** must be between 0 and 100.',
          'Readings also arrive on their own during a Skydio sync.',
          'Readings are not edited or removed one at a time. If you delete the battery, its readings go with it. If you merge a duplicate battery into another, its readings move to the battery you keep.',
          'Admins and supervisors can record readings by default. Everyone who can view the fleet sees the chart.',
        ],
      },
      {
        id: 'other-equipment',
        title: 'Controllers, docks, sensors, attachments and other equipment',
        summary: 'These tabs follow the same steps as vehicles. Each item has its own page with notes, maintenance history and documents.',
        steps: [
          'Open the tab, then choose **Add Controller**, **Add Dock**, **Add Sensor**, **Add Attachment** or **Add Other Item**.',
          'Fill in the boxes. Only **Serial Number** is required, except on **Other**, where **Name** is required.',
          'Click an item\'s name to open its page. Choose the pencil icon there to edit it.',
        ],
        notes: [
          '**Controllers** can have an **Assigned Pilot**. Set it on the controller\'s page. The page shows the pilot, the status and the date of the last maintenance.',
          '**Docks** have a **Location Name**, and **Latitude** and **Longitude** if you know them. When both coordinates are set, the dock\'s page shows a **Location** map.',
          '**Sensors** and **Attachments** have a **Type**, a **Manufacturer** and a **Model**. Their pages show **Total Flights**, **Total Hours**, **Unique Pilots** and a **Flight History**.',
          '**Other** is for anything else you track, such as a case or a charger. It has a **Name**, a **Category** and a **Serial Number**.',
          'The **Status** choices are **Active** and **Maintenance**, plus **Retired** and **Damaged**. Docks also offer **Online** and **Offline**.',
          'Emptying an optional box in an edit clears the value on the record.',
        ],
      },
      {
        id: 'components',
        title: 'Components',
        summary: 'Use components to track the parts on one aircraft, such as propellers, motors and gimbals, with their flight hours and warranty.',
        steps: [
          'Open the vehicle\'s page and find the **Components** card.',
          'Choose **Add Component**.',
          'Enter a **Name** (required) and pick a **Type**: **Propeller**, **Motor**, **Gimbal**, **Camera**, **Frame**, **Landing Gear** or **Other**.',
          'Fill in anything else you know: **Serial Number**, **Manufacturer**, **Model**, **Status**, **Install Date**, **Flight Hours**, **Max Flight Hours**, **Warranty Expiry**, **Replacement Cost** and **Notes**.',
          'Choose **Save Component**.',
        ],
        notes: [
          'The **Status** choices are **Active**, **Needs Replacement**, **Replaced** and **Retired**.',
          '**Flight Hours** is a number you keep up to date. The app does not add flight time to it for you.',
          'When **Max Flight Hours** is set, the table shows hours as "used / max" and turns amber once the part reaches 90 percent of its limit.',
          'Use the trash icon (**Delete component**) to remove a component, then confirm. A component cannot be edited, so delete it and add it again to change it.',
          'Only people who can manage the fleet add or delete components: admins and supervisors by default. Everyone who can view the fleet can read the list.',
        ],
      },
      {
        id: 'equipment-dropdowns',
        title: 'Equipment lists on flight forms',
        summary: 'When you add or edit a flight, the equipment boxes offer your fleet records, so you pick equipment instead of typing it.',
        steps: [
          'In the flight form, click **Battery**, **Sensor Package** or one of the **Attachment** boxes.',
          'Pick an item from the list, or type to narrow it down.',
        ],
        notes: [
          'If you type a serial number the fleet does not have yet, saving the flight adds a fleet record for it.',
          'Retired and damaged equipment still appears in these lists. Take care to pick the equipment you really flew.',
        ],
      },
      {
        id: 'merging-duplicates',
        title: 'Merging duplicate equipment',
        summary: 'Use this when two records describe the same item, for example after a provider sync created a second copy of an aircraft or battery. You keep one record and absorb the other into it.',
        steps: [
          'On **Fleet**, open the **Vehicles**, **Batteries**, **Sensors** or **Attachments** tab.',
          'Find the record you want to keep. Choose the merge icon (**Merge**) on its row.',
          'In the **Merge** dialog, open **Merge from (duplicate to remove)** and pick the duplicate.',
          'Choose **Merge**.',
        ],
        notes: [
          'The duplicate is deleted. Its flights, and the records that point at it, are moved to the record you kept. A message tells you the result.',
          'For a vehicle, this also moves flight plans, incidents, mission and training logs, documents, registrations, components, maintenance and checkouts. If the duplicate has an **API Serial** and the kept vehicle has none, the kept vehicle takes it, so the next provider sync matches it.',
          'Batteries also move their health readings.',
          'Merging cannot be undone. Check which record you are keeping before you choose **Merge**.',
          'Controllers, docks and other equipment have no merge icon.',
          'Admins and supervisors can merge by default.',
        ],
      },
    ]
  },
  {
    id: 'registrations',
    title: 'FAA Registrations',
    topics: [
      {
        id: 'faa-registrations',
        title: 'FAA registrations on a vehicle',
        summary: 'Each vehicle keeps its FAA registrations on its own page, so you can see when the current one expires and what came before it.',
        image: {
          src: '/manual/registrations-faa-registrations.png',
          alt: 'The FAA Registration card of a vehicle with a Next Due banner, the days remaining, and a table of one current and one expired registration',
          caption: 'The FAA Registration card: the Next Due banner above the list of registrations.',
        },
        steps: [
          'On **Fleet**, click the vehicle\'s name and find the **FAA Registration** card.',
          'The banner at the top shows **Next Due** (the expiry date of the current registration), the registration number and the date it was registered.',
          'The badge at the right shows the days remaining, or **Overdue** with the number of days past.',
          'The table lists every registration with **Reg #**, **Registered**, **Expires**, **Status** and **Notes**.',
        ],
        notes: [
          'The badge is green with more than 90 days left, amber with 90 days or fewer, and red with under 30 days or overdue.',
          'A vehicle has one **Current** registration at a time. Older ones show **Previous**. Any registration whose expiry date has passed shows **Expired**, even if it is the current one.',
          'The same due date and number show in the **Next Due** and **FAA Reg** columns on the Fleet page.',
          'The email digest lists current registrations that expire in the next 30 days.',
          'Everyone who can view registrations sees the card. By default that is admins, supervisors, pilots and viewers.',
        ],
      },
      {
        id: 'adding-a-registration',
        title: 'Adding a registration',
        summary: 'Add a registration when a vehicle is first registered and again each time you renew it. The new one becomes the current one.',
        steps: [
          'Open the vehicle\'s page and find the **FAA Registration** card.',
          'Choose **Add Registration**.',
          'Enter the **Registration #** (it usually starts with FA) and the **Registration Date**.',
          'Check **Expiry (auto: +3 years)**. It shows the date three years after the registration date. You cannot type in it.',
          'Add **Notes** if you like, then choose **Save Registration**.',
        ],
        notes: [
          'Give at least a registration number or a registration date. With a date, the app sets the expiry three years later. With only a number, there is no expiry date and no countdown.',
          'Saving a new registration makes it the current one. The one before it becomes **Previous**.',
          'A registration cannot be edited. To fix a mistake, delete it with the trash icon (**Delete registration**) and add it again. If you delete the current registration, the newest remaining one by registration date becomes current.',
          'Adding and deleting registrations is for admins only by default. Supervisors and pilots can see registrations but not change them. An admin can change this under **Settings**.',
          'The **FAA Registration** text box in a vehicle\'s edit form is a separate note. The card and the Fleet list use the registrations you add here, and the list falls back to that text when there are none.',
        ],
      },
    ]
  },
  {
    id: 'fleet-health',
    title: 'Fleet Health',
    topics: [
      {
        id: 'reading-fleet-health',
        title: 'Reading the Fleet Health page',
        summary: 'Fleet Health gives a quick picture of how hard each vehicle is used and how healthy your batteries are.',
        image: {
          src: '/manual/fleet-health-reading-fleet-health.png',
          alt: 'The Fleet Health page with five summary cards, a Vehicle Utilization table and a Battery Health bar chart with a Good, Fair and Poor legend',
          caption: 'The Fleet Health page: summary cards, vehicle utilization and battery health.',
        },
        steps: [
          'Press Ctrl+K (Cmd+K on a Mac), type Fleet Health and press Enter. The page has no sidebar link.',
          'Read the five cards: **Vehicles in Service**, **Batteries in Service**, **Avg Battery Health**, **Overdue Maintenance** and **Total Flight Hours**.',
          'In **Vehicle Utilization**, click a heading (**Vehicle**, **Flights**, **Hours**, **Last Flight** or **Overdue**) to sort. Click a vehicle to open it.',
          'In **Battery Health**, each bar is one battery. Green means above 80 percent (**Good**), amber 50 to 80 (**Fair**) and red under 50 (**Poor**).',
        ],
        notes: [
          '"In service" means not retired and not damaged. A vehicle in **Maintenance** still counts.',
          'Flights and hours count only flights that count toward your unit\'s totals.',
          '**Avg Battery Health** averages only the batteries that have a health figure. A battery that was never measured is left out, not counted as 0 percent. It shows as an empty bar.',
          '**Overdue Maintenance** counts every overdue maintenance schedule in the unit, for vehicles and for other equipment.',
          'Only people who can view maintenance see each vehicle\'s own overdue count. For others the **Overdue** column reads **OK**, but the **Overdue Maintenance** card still shows the unit total.',
          'Everyone who can view the fleet can open this page.',
        ],
      },
    ]
  },
  {
    id: 'checkouts',
    title: 'Equipment Checkouts',
    topics: [
      {
        id: 'checking-equipment-out',
        title: 'Checking equipment out',
        summary: 'Use a checkout to record who has a piece of equipment, so you always know where it is.',
        image: {
          src: '/manual/checkouts-checking-equipment-out.png',
          alt: 'The Check Out Equipment dialog with type, item, pilot, expected return and notes',
          caption: 'The Check Out Equipment dialog.',
        },
        steps: [
          'Choose **Checkouts** in the sidebar, then **Check Out**.',
          'Pick the **Type**: **Vehicle**, **Battery**, **Controller**, **Dock**, **Sensor**, **Attachment** or **Other**.',
          'Pick the **Item**.',
          'Pick the **Pilot** who is taking it. The box starts on your own pilot record, if you have one.',
          'Optional: **Expected return (optional)** and **Notes (optional)**.',
          'Choose **Check Out**.',
        ],
        notes: [
          'You can pick any active pilot. A supervisor can record a checkout for someone else. The audit log shows who entered the record and who has the equipment.',
          'The **Item** list shows only equipment that is not retired or damaged.',
          'Equipment that is already out cannot be checked out again until it is checked in. The app says "This equipment is already checked out".',
          'Supervisors and pilots can check equipment out by default, and so can admins. Viewers can see the page but not the buttons.',
          'The page shows checkouts only to roles that can view the fleet.',
        ],
      },
      {
        id: 'checking-equipment-back-in',
        title: 'Checking equipment back in',
        summary: 'Check equipment in when it comes back, so the record shows it is available again.',
        steps: [
          'On **Checkouts**, find the item under **Currently Out**.',
          'Choose **Check In** on its row.',
          'Under **Returned by**, pick who is returning it. It starts on the person who took it out, or on you.',
          'Add **Notes (optional)** if you like.',
          'Choose **Check In**.',
        ],
        notes: [
          'Anyone who can check out can check in, including equipment someone else took.',
          'The record keeps the date it went out, who took it, the date it came back and who returned it.',
        ],
      },
      {
        id: 'active-and-returned-records',
        title: 'Active and returned records',
        summary: 'The Checkouts page shows what is out now and keeps a history of what has been out before.',
        image: {
          src: '/manual/checkouts-active-and-returned-records.png',
          alt: 'The Checkouts page with a Currently Out table and a History table with the Show returned box',
          caption: 'The Checkouts page: Currently Out above History.',
        },
        steps: [
          '**Currently Out** lists everything that has not come back. Each row shows the equipment, its type, who holds it, when it went out and the expected return date.',
          '**History** starts with the items still out. Tick **Show returned** to add the ones that have come back.',
        ],
        notes: [
          'In **History**, an item that is still out shows **Out** in the **Returned** column.',
          'A trash icon at the end of a **History** row deletes that record for good, after you confirm. Admins and supervisors can do this by default. Pilots and viewers cannot.',
          'When a vehicle is checked out, its location on the dashboard changes to "with" that pilot. See **Where a drone is**.',
        ],
      },
    ]
  },
  {
    id: 'locations',
    title: 'Drone Locations',
    topics: [
      {
        id: 'last-known-location',
        title: 'Where a drone is',
        summary: 'The Locations card on the dashboard shows the last known place of every drone that is not retired.',
        steps: [
          'Open the **Dashboard**.',
          'Find the **Locations** card. Each drone shows its name and its location under it.',
        ],
        notes: [
          'A location is "with" a pilot name, or a place name such as North. It shows whichever was recorded most recently: a checkout, or a location someone set by hand.',
          'After a drone is checked in, it reads **Returned**, until someone sets a location again. The place set before it went out is out of date.',
          '**Unknown** means no checkout or location was ever recorded.',
          'If you have no drones, the card says **No drones**.',
          'Everyone who can view the fleet sees the card.',
        ],
      },
      {
        id: 'setting-a-location',
        title: 'Setting a location',
        summary: 'Update a drone\'s location when it moves, without a full checkout.',
        steps: [
          'On the **Locations** card, find the drone.',
          'Open **Set location…** beside it.',
          'Choose a place under **Places**, or a pilot under **Pilots**.',
          'The card updates at once.',
        ],
        notes: [
          'A drone is in one spot at a time: one place or one pilot.',
          'Supervisors and pilots can set a location by default, and so can admins. Viewers cannot. An admin can change this under **Settings**.',
          'An admin sets the list of places under **Settings**, in **Drone Locations**. If it was never changed, the places are North, Central and South.',
          'Each change is saved in the audit log with who made it.',
        ],
      },
    ]
  },
  {
    id: 'missions',
    title: 'Mission Log',
    topics: [
      {
        id: 'mission-log',
        title: 'Finding missions',
        summary: 'The **Mission Log** records work that is not a single flight: callouts, searches, demonstrations and other operations, with who took part and for how many hours.',
        steps: [
          'Choose **Mission Log** in the sidebar.',
          'Type in **Search missions...** to find a word in a mission.',
          'Use the two date boxes to show a range of dates, and the pilot box (it starts at **All Pilots**) to show one pilot\'s missions.',
          'Click a row to open it. You see the description, case number, start and end times, notes and each pilot with their role. Click it again to close it.',
        ],
        notes: [
          'The list shows the 200 most recent matches. If it says so under the table, narrow the dates or the search to reach older missions.',
          'Each row shows the date, title, reason, location, drone, pilots, man hours and status. Some columns are hidden on a narrow screen.',
          'Status is **Planned**, **In Progress**, **Completed** or **Cancelled**.',
          'Choose **Export CSV** to download a CSV file (a table you can open in a spreadsheet). It holds all missions, not only the ones you filtered to.',
          'Everyone can see the log by default, including viewers.',
        ],
      },
      {
        id: 'adding-missions',
        title: 'Adding and changing a mission',
        summary: 'Add a mission after the work is done, or plan one ahead and change its status later.',
        image: {
          src: '/manual/missions-adding-missions.png',
          alt: 'The Add Mission dialog with date, status, title, reason, location, hours, drone and pilots involved',
          caption: 'The Add Mission dialog, with one pilot added.',
        },
        steps: [
          'On **Mission Log**, choose **Add Mission**.',
          'Check the **Date** (it starts as today) and set the **Status**.',
          'Type a **Title**. The **Date** and **Title** are required.',
          'Pick a **Reason / Purpose** from the list. Choose **Other...** to type your own.',
          'Fill in what you know: **Location**, **Case Number**, **Man Hours**, **Start Time**, **End Time**, **Drone Used**, **Description** and **Notes**.',
          'Under **Pilots Involved**, choose **+ Add Pilot**. Pick the pilot, pick a role (**PIC**, **Observer**, **Spotter**, **Visual Observer** or **Support**) and enter their hours. Use the X to remove a line.',
          'Choose **Add Mission**.',
          'To change a mission later, open its row and choose **Edit Mission**, then **Save Changes**.',
          'To remove one, choose the trash icon at the end of its row and confirm.',
        ],
        notes: [
          'Supervisors and pilots can add missions by default. Viewers cannot.',
          'Supervisors can change or delete any mission by default. Pilots can change or delete only their own: missions they created, or missions their pilot record is on.',
          'An admin can change who may add and edit under **Settings**.',
          'The **Reason / Purpose** list is the same list used for flights.',
        ],
      },
      {
        id: 'importing-missions',
        title: 'Importing missions from a file',
        summary: 'If you kept missions in a spreadsheet, an admin can bring them in instead of typing each one.',
        steps: [
          'On **Mission Log**, choose **Import**.',
          'Choose a CSV or Excel file.',
          'The window lists each field the app uses. Next to each, pick the column from your file that holds it. The app suggests matches. Choose "don\'t map" for fields you do not have.',
          'Fields marked required must be matched. The button stays greyed out until they are.',
          'Choose the **Import** button that shows the row count.',
          'Read the summary, then choose **Done**.',
        ],
        notes: [
          'Only admins see **Import**.',
          'The summary tells you how many records were created, how many were skipped for a missing date, how many were already imported, and which names or drones it could not match.',
          'Names that are not in your pilot list are recorded as Unknown. Rows for drones that are not in your fleet are skipped. Add the missing pilots or drones first if that matters.',
          'There is a limit on how many rows can come in at once. If the window says so, split the file and import the rest.',
        ],
      },
    ]
  },
  {
    id: 'training',
    title: 'Training Log',
    topics: [
      {
        id: 'training-log',
        title: 'Finding training entries',
        summary: 'The **Training Log** records training events: who trained, what kind of training it was, who taught it, for how long and how it went.',
        steps: [
          'Choose **Training Log** in the sidebar.',
          'Type in **Search training...** to look through titles, types, locations, instructors and pilot names.',
          'Use the two date boxes, the pilot box (**All Pilots**) and the type box (**All Types**) to narrow the list.',
          'Click a row to open it. You see the description, drone, objectives, start and end times, notes and each pilot with their role. Click it again to close it.',
        ],
        notes: [
          'Each row shows the date, title, type, instructor, location, pilots, man hours and outcome. Some columns are hidden on a narrow screen.',
          'The types are **Initial**, **Recurrent**, **Proficiency** and **Special**. The outcome is **Completed**, **Incomplete** or **Failed**.',
          'The log loads up to 200 entries at a time. The search looks only through the entries that are loaded, so narrow the dates first if you have many.',
          'Choose **Export CSV** to download a CSV file (a table you can open in a spreadsheet). It holds all training entries, not only the ones you filtered to.',
          'Everyone can see the log by default, including viewers.',
        ],
      },
      {
        id: 'adding-training',
        title: 'Adding and changing a training entry',
        summary: 'Add an entry after a training session so there is a record of who took part and how it went.',
        image: {
          src: '/manual/training-adding-training.png',
          alt: 'The Add Training dialog with date, type, outcome, title, instructor, objectives and pilots or trainees',
          caption: 'The Add Training dialog, with one pilot added.',
        },
        steps: [
          'On **Training Log**, choose **Add Training**.',
          'Check the **Date**. Pick the **Training Type** and the **Outcome**.',
          'Type a **Title**. The **Date**, **Training Type** and **Title** are required.',
          'Fill in what you know: **Location**, **Instructor**, **Man Hours**, **Start Time**, **End Time**, **Drone Used**, **Description**, **Objectives** and **Notes**.',
          'Under **Pilots / Trainees**, choose **+ Add Pilot**. Pick the pilot, pick a role and enter their hours. Training has one more role than missions: **Student**.',
          'Choose **Add Training**.',
          'To change an entry later, open its row and choose **Edit Training**, then **Save Changes**.',
          'To remove one, choose the trash icon at the end of its row and confirm.',
        ],
        notes: [
          'Supervisors and pilots can add entries by default. Viewers cannot.',
          'Supervisors can change or delete any entry by default. Pilots can change or delete only their own: entries they created, or entries their pilot record is on.',
          'An admin can change who may add and edit under **Settings**. Missions and training share the same permissions.',
        ],
      },
      {
        id: 'importing-training',
        title: 'Importing training from a file',
        summary: 'If you kept training records in a spreadsheet, an admin can bring them in instead of typing each one.',
        steps: [
          'On **Training Log**, choose **Import**.',
          'Choose a CSV or Excel file.',
          'Next to each app field, pick the column from your file that holds it, or choose "don\'t map".',
          'Match every field marked required, then choose the **Import** button that shows the row count.',
          'Read the summary, then choose **Done**.',
        ],
        notes: [
          'Only admins see **Import**.',
          'It works the same way as the mission import. See **Importing missions from a file** for what the summary means.',
        ],
      },
    ]
  },
  {
    id: 'pilots',
    title: 'Pilots',
    topics: [
      {
        id: 'pilot-list',
        title: 'The Pilots page',
        summary: 'Use the **Pilots** page to find a pilot, add a new one, or tidy up the list. Click a name to open that pilot\'s profile.',
        steps: [
          'Open **Pilots** in the sidebar.',
          'Type in **Search pilots...** to filter by name, email or badge number.',
          'Click a column heading (**Name**, **Email**, **Badge #** or **Status**) to sort. Click it again to reverse the order.',
          'To add a pilot, click **Add Pilot**, fill in **First Name** and **Last Name** (the only required fields), and click **Add Pilot** in the dialog.',
          'To change a pilot, click the pencil in the **Actions** column, change the fields and click **Update**.',
          'To combine two records for the same person, click the merge icon, choose the record to keep under **Keep this pilot**, and click **Merge**.',
          'To retire a pilot, click the bin icon and confirm **Deactivate**.',
        ],
        notes: [
          'Everyone can see the list. **Add Pilot**, merge, deactivate and **Export CSV** are for supervisors and admins by default. **Export CSV** also needs the permission to export reports. A CSV file is a plain table that opens in Excel.',
          'Supervisors and admins can edit any pilot. Pilots can edit only their own profile. An admin can change this under **Settings**.',
          'Email and phone numbers are hidden from viewers by default. Without that access the **Email** column shows a dash and the email and cell fields are missing from the dialog.',
          'Each badge number can belong to one pilot only.',
          '**Merge** moves every flight, log, certification and record from one pilot to the other, then removes the first. It cannot be undone.',
          '**Deactivate** does not delete anything. The pilot is marked inactive, and drops off the Certifications matrix and out of the compliance counts. Flights stay on record. Set **Status** back to **Active** in the edit dialog to bring the pilot back.',
          '**Counts towards unit totals** (supervisors and admins only) is a separate switch. Turn it off for a vendor or guest operator: their flights stay on record but leave the unit\'s numbers.',
        ],
      },
      {
        id: 'pilot-profiles',
        title: 'The pilot profile',
        summary: 'A pilot\'s profile page gathers their details, flight totals, certifications and currency in one place.',
        image: {
          src: '/manual/pilots-pilot-profiles.png',
          alt: 'The profile card of a demo pilot with initials, name, email, a personal cell number and an active status badge',
          caption: 'The profile card at the top of a pilot page.',
        },
        steps: [
          'On **Pilots**, click the pilot\'s name.',
          'The card at the top shows the photo (or initials), name, email, **Personal Cell**, **Work Cell**, badge number, status and notes.',
          'Below it you see **Total Flights**, **Flight Hours** and **Avg Duration**, then tiles for training hours, mission hours and incidents, and the **Flights by Month** and **Flights by Purpose** charts.',
          'Further down are **Needs Attention**, **Recent Flights** (the latest 20), **Certifications**, **Currency Status** and **Documents**.',
          'Click **Back to Pilots** to return to the list.',
        ],
        notes: [
          'You only see the parts you may view. For example, someone without access to flights does not see the flight totals, charts or **Recent Flights**.',
          'Only admins can add or replace the photo. Click the small camera on the photo and choose an image file. The photo shows on this page. The list shows initials.',
          'Email and phone numbers are hidden from roles without contact access (viewers by default).',
          'The **Currency Status** card appears only when at least one active currency rule exists.',
        ],
      },
      {
        id: 'editing-a-profile',
        title: 'Editing a pilot profile',
        summary: 'Update a pilot\'s name, contact details, badge number or notes from their profile page.',
        steps: [
          'Open the pilot\'s profile and click the pencil next to the name (**Edit profile**).',
          'Change **First Name**, **Last Name**, **Email**, **Personal Cell**, **Work Cell**, **Badge Number** or **Notes**.',
          'Click **Save**, or **Cancel** to throw the changes away.',
        ],
        notes: [
          'The pencil shows only if you may edit this pilot. Supervisors and admins can edit anyone. A pilot can edit only the profile linked to their own account. Viewers cannot edit.',
          '**Status** appears only for supervisors and admins. A pilot cannot change their own status, the unit totals setting or the photo.',
          'The email and cell fields appear only for roles with contact access. Without it they are left out of the form and your save does not touch them.',
          'First and last name are required.',
        ],
      },
      {
        id: 'pilot-currency',
        title: 'Pilot currency',
        summary: 'Currency means a pilot has flown enough recently. A currency rule sets the flight hours (and, if you want, the number of flights) a pilot must log within a number of days, for example 5 hours in 90 days.',
        image: {
          src: '/manual/pilots-pilot-currency.png',
          alt: 'The New Currency Rule dialog with a name, required hours, period in days and minimum flights filled in',
          caption: 'The New Currency Rule dialog in Settings.',
        },
        steps: [
          'Open **Settings** (admins only) and scroll to **Currency Rules** on the **General** tab.',
          'Click **New Rule**.',
          'Enter a **Name**. Add a **Description (optional)** if you like.',
          'Enter **Required hours** and **Period (days)**. Add **Minimum flights (optional)** if the rule also needs a number of flights.',
          'Leave **Vehicle model (optional)** blank to count every aircraft, or type a model (for example X10) to count only flights on that model.',
          'Leave **Active (include in pilot currency calculations)** ticked and click **Create**.',
          'To change or remove a rule, use the pencil or bin next to it in the list. Editing saves with **Save**.',
        ],
        notes: [
          'Once a rule is active, every pilot page shows a **Currency Status** card. Each row shows the hours and flights flown against the rule, **Current** or **Lapsed**, and an **Expires** date: the day the pilot would lapse if they did not fly again.',
          'A pilot is **Lapsed** if any active rule is not met. With no active rules everyone counts as current.',
          'Only reviewed flights count, from every source. A flight waiting for review, including one sent back to the queue after an edit, does not count until a supervisor reviews it. A pilot can show as lapsed while flights wait for review.',
          'A rule can look back up to 3650 days.',
          'Lapsed pilots appear in **Needs Attention** on their page and on the **Compliance** page.',
        ],
      },
      {
        id: 'needs-attention',
        title: 'Needs Attention',
        summary: 'The **Needs Attention** card on a pilot page lists what that pilot should fix: lapsed currency and certifications that are expired or about to expire.',
        image: {
          src: '/manual/pilots-needs-attention.png',
          alt: 'The Needs Attention card of a demo pilot listing a certification that expires soon, with the number of items in the header',
          caption: 'The Needs Attention card with one item listed.',
        },
        steps: [
          'Open the pilot\'s page and find the **Needs Attention** card.',
          'Each line is one item. Red lines are lapsed currency or an expired certification. Amber lines are certifications expiring within 30 days, with the days left.',
          'The number in the card header is how many items there are.',
        ],
        notes: [
          'When nothing is outstanding the card says **All clear**.',
          'The card shows only for people who may view certifications.',
          'A certification you have renewed no longer shows. Only the current record counts. Certifications marked not issued are left out too.',
          'Certifications without an expiration date never appear.',
        ],
      },
    ]
  },
  {
    id: 'certifications',
    title: 'Certifications',
    topics: [
      {
        id: 'certification-types',
        title: 'Certification types',
        summary: 'A certification type is a kind of credential you track, such as Part 107, a training course or an insurance card. Set up the types first, then assign them to pilots.',
        steps: [
          'Open **Certifications** and click the **Cert Types** tab.',
          'Click **Add Type**.',
          'Enter the **Name** and pick a **Category** (FAA, NIST, Equipment, Insurance, Training or Custom).',
          'Leave **Has Expiration Date** ticked if the credential runs out. Enter the **Renewal Period (months)**, for example 24.',
          'Add a **Description** if useful, then click **Add**.',
          'Each card on the tab has an eye icon (hide or show), a pencil (**Edit**) and a bin (**Delete**).',
        ],
        notes: [
          'Supervisors and admins manage types. Everyone else can look.',
          'Hiding a type takes its column off the matrix but keeps every pilot record. Use the eye again to show it. Hidden types show a **Hidden** label.',
          'The renewal period fills in the new expiry date when you renew.',
          'Admins can rename the status names that show on the matrix under **Settings**, **Certification Status Labels**.',
        ],
      },
      {
        id: 'certification-matrix',
        title: 'The certification matrix',
        summary: 'The matrix is a grid of pilots down the side and certification types across the top. Each cell shows one pilot\'s status for one certification, so you can see gaps at a glance.',
        image: {
          src: '/manual/certifications-certification-matrix.png',
          alt: 'The certification matrix with demo pilots down the side and certification types across the top, cells coloured green, amber and red with expiry dates',
          caption: 'The matrix: green is fine, amber is expiring soon, red is expired.',
        },
        steps: [
          'Open **Certifications**. The **Certification Matrix** tab is the first one.',
          'Read each cell: a coloured status and, below it, the expiry date.',
          'Narrow the grid with **Search pilots...**, the status list (**All Statuses**), the category list (**All Categories**) or the **Hide empty** box. The count at the right shows how many pilots and columns you see.',
          'Click a pilot\'s name to open their profile.',
        ],
        notes: [
          'Amber **expiring soon** means the expiry date is within 90 days. Red **expired** means the date has passed. Green means complete or active. Grey means not started, not issued or not eligible.',
          'The matrix lists active pilots only. Deactivated pilots are not shown.',
          'A renewed certification does not show. The cell shows the newer record.',
          '**Hide empty** hides pilots who have no certification record at all.',
          'Supervisors and admins see arrows in each column heading to move the column left or right.',
          'The status list keeps pilots who have at least one cell with that status. All their columns still show.',
          '**Export CSV** needs the permission to export reports.',
        ],
      },
      {
        id: 'assigning-a-certification',
        title: 'Assigning a certification',
        summary: 'Assign a certification to a pilot when they first hold it, or to start tracking one they are working toward.',
        steps: [
          'On the matrix, click the empty cell for that pilot and certification. The dialog opens with both already chosen. Or click **Assign Cert** and pick them yourself.',
          'Choose the **Status**.',
          'Fill in **Issue Date**, **Expiration Date** and **Certificate Number** if you have them. A **NIST Level** field shows for NIST types.',
          'Add **Notes** if useful, then click **Assign**.',
        ],
        notes: [
          'Supervisors and admins only.',
          'A pilot can hold one current record per certification. A second one is refused with a message to edit or renew the existing one.',
          'The expiry date cannot be before the issue date.',
          'To attach the certificate scan, open the saved certification (see Editing a certification) and use the document box at the bottom.',
        ],
      },
      {
        id: 'editing-a-certification',
        title: 'Editing a certification',
        summary: 'Fix a date, a number or a note on a certification that already exists.',
        image: {
          src: '/manual/certifications-editing-a-certification.png',
          alt: 'The Edit Certification dialog for a demo pilot with status, issue date, expiration date, certificate number, notes, and the Update, Renew, Remove and Cancel buttons',
          caption: 'The Edit Certification dialog, opened from a matrix cell.',
        },
        steps: [
          'On the matrix, click the cell that holds the certification.',
          'The **Edit Certification** dialog opens with everything saved so far, including the notes.',
          'Change **Status**, **Issue Date**, **Expiration Date**, **Certificate Number** or **Notes**.',
          'Click **Update**.',
          'To take the certification off the pilot, click **Remove** and confirm.',
        ],
        notes: [
          'To clear a field, empty it and click **Update**. The date, certificate number or notes are then saved as empty.',
          'The pilot and the certification type are locked when editing.',
          '**Remove** deletes the certification together with its renewal history. Attached documents are kept. This cannot be undone.',
          'Supervisors and admins can edit. For everyone else, clicking a filled cell opens **Certification Documents** instead, where you can view documents and upload for your own certifications if you have file access.',
          'The dialog also holds the documents for that certification and the **Renewal History**.',
        ],
      },
      {
        id: 'renewing-a-certification',
        title: 'Renewing a certification',
        summary: 'Renew when a pilot gets a new certificate. The old record is kept as history and a fresh one takes its place.',
        image: {
          src: '/manual/certifications-renewing-a-certification.png',
          alt: 'The renewal form inside the Edit Certification dialog with new issue date, new expiration, certificate number and notes',
          caption: 'The renewal form: enter the new issue date and the expiry fills in.',
        },
        steps: [
          'Click the pilot\'s cell on the matrix and click **Renew** in the dialog.',
          'Enter **New Issue Date**. **New Expiration** fills in from the type\'s renewal period. You can change it.',
          'Check **Certificate Number** (it carries over from the old record) and add **Notes** if needed.',
          'Click **Renew Certification**. **Back** returns to the normal form.',
        ],
        notes: [
          'The old record is archived with the status renewed and the new one is created as complete.',
          'Renewed records no longer show on the matrix, in **Needs Attention**, in the compliance counts or on the **Calendar**. Only the current record does.',
          'The **Renew** button is missing for types that do not expire.',
          'The new issue date is required.',
        ],
      },
      {
        id: 'bulk-renewal',
        title: 'Renewing several at once',
        summary: 'After a training day, renew many certifications with one issue date.',
        steps: [
          'On the matrix, tick the small box in each cell you want to renew.',
          'In the bar that appears (for example **3 selected**), click **Renew selected**.',
          'Check **Issue date** (it starts as today), add **Notes (optional)**, and click **Renew All**.',
          '**Clear** unticks everything without renewing.',
        ],
        notes: [
          'Supervisors and admins only. Cells for types that never expire have no box.',
          'Each certification gets its own new expiry date from its type\'s renewal period. A type with no renewal period gets no expiry date.',
          'Records that are already renewed are skipped.',
        ],
      },
      {
        id: 'renewal-history',
        title: 'Renewal history',
        summary: 'See every earlier record behind a certification, so you know when it was renewed before.',
        steps: [
          'Click the cell on the matrix.',
          'Scroll to **Renewal History** in the dialog. Each line shows the earlier issue date, expiry date and status.',
        ],
        notes: [
          'The list appears only when the certification has been renewed at least once.',
          'The pilot\'s own page shows only the current records in its **Certifications** table.',
        ],
      },
      {
        id: 'tracking-expirations',
        title: 'Where expiring certifications show up',
        summary: 'Expiry dates feed several places, each with its own warning window.',
        notes: [
          'The matrix turns a cell amber 90 days before expiry and red after it.',
          'The **Compliance** page counts pilots with an expired certification (**Expired Certs**) and lists certifications expiring within 90 days (**Expiring Soon**).',
          'The **Needs Attention** card on a pilot page flags certifications expiring within 30 days.',
          'The **Calendar** shows each expiry date as an event.',
          'The matrix, compliance counts and calendar skip renewed records, certifications marked not issued, and deactivated pilots.',
        ],
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
        title: 'Getting a weather briefing',
        summary: 'Use the Weather page before a flight to check wind, visibility, cloud height and the next 12 hours for the place you plan to fly. It ends in a single answer: GO, CAUTION or NO-GO.',
        steps: [
          'Choose **Weather** in the sidebar. The page opens on your unit\'s default place and loads a briefing at once.',
          'To check another place, type an address, or two numbers such as 40.7128, -74.0060, into **Coordinates or Address**.',
          'Or click the small map to drop a pin. The address box fills in for you.',
          'Or type numbers into **Latitude** and **Longitude**.',
          'To use where you are now, choose **GPS** and allow your browser to share your location.',
          'Choose **Check Weather**.',
          'Read the colored answer at the top, then the reasons listed under it.',
        ],
        notes: [
          'Everyone who can sign in can use the Weather page.',
          'The server fetches the weather from public services, so the page needs the internet.',
          'If an address is not found, you see No match for that address. Try a nearby town or use numbers.',
        ],
      },
      {
        id: 'default-and-recent-places',
        title: 'Default place and recent places',
        summary: 'The page starts on your unit\'s default place, and remembers the places you check so you can return to them in one click.',
        steps: [
          'Look at **Recent Locations** under the form. It lists up to eight places you checked on this device.',
          'Click one to load its briefing again.',
        ],
        notes: [
          'The default place is the **Default Location** an admin sets in **Settings**. If none is set, the page starts on the White House in Washington, D.C.',
          '**Recent Locations** is kept in your browser. It is not shared with other people or other devices.',
        ],
      },
      {
        id: 'go-no-go-advisory',
        title: 'GO, CAUTION and NO-GO',
        summary: 'The colored panel at the top gives a quick answer for flying at that place now. It is an aid for your own judgment, not an order.',
        steps: [
          'Read the label: green **GO**, amber **CAUTION**, red **NO-GO**, or grey **UNKNOWN** when no weather data came back.',
          'Read the reasons listed under it. Each one names the reading that moved the answer.',
          'Read **Current Conditions** for wind, gusts, temperature, humidity, visibility, ceiling (height of the lowest cloud layer above the ground), flight category and rain.',
        ],
        notes: [
          'Out of the box, wind over 15 mph or gusts over 20 mph give CAUTION, and wind over 25 mph or gusts over 30 mph give NO-GO.',
          'Visibility under 3 miles gives CAUTION and under 1 mile gives NO-GO. A ceiling under 500 feet gives CAUTION and under 200 feet gives NO-GO.',
          'Temperature under 32 F or over 100 F gives CAUTION, and under 20 F gives NO-GO. Rain of more than 0.01 inch gives CAUTION.',
          'An admin can change these limits under **Weather Thresholds** in **Settings**.',
          'The flight category is a standard aviation label: VFR is good, MVFR is marginal, IFR is poor and LIFR is very poor.',
        ],
      },
      {
        id: 'forecast-and-reports',
        title: 'The forecast and the airport reports',
        summary: 'Below the answer you get a 12-hour forecast and the raw airport reports, for when you want more than the summary.',
        steps: [
          'Read **Nearest METAR Station** for the airport the readings come from and how far away it is. A METAR is the latest observation at that airport.',
          'Scroll to **12-Hour Forecast** for charts of wind and gusts, and of temperature and chance of rain.',
          'Scroll the **Hourly Detail** cards sideways to see each hour.',
          'Open **Raw METAR** or **Raw TAF (Terminal Forecast)** to read the original text. A TAF is that airport\'s forecast.',
        ],
        notes: [
          'The raw sections appear only when a station near the place has reported.',
          'The readings are from the nearest airport, which may be some miles from your site.',
        ],
      },
    ]
  },
  {
    id: 'airspace',
    title: 'Airspace (ADS-B)',
    topics: [
      {
        id: 'live-aircraft-map',
        title: 'Watching nearby aircraft',
        summary: 'The Airspace page shows planes and helicopters flying near a place you pick. Use it to see manned traffic before and during a flight. It uses ADS-B, a signal most aircraft broadcast with their position and height.',
        steps: [
          'Choose **Airspace** in the sidebar. The map opens on your unit\'s default place.',
          'Click the map where you plan to fly. A dashed circle shows the search area.',
          'Wait for the aircraft to appear. The top bar shows how many were found and when.',
          'Click an aircraft to see its call sign, type, registration, height, speed, heading, climb rate and squawk code. A squawk is a four-digit code the pilot sets.',
          'If an aircraft reports an emergency, the popup says so in red.',
        ],
        notes: [
          'Nothing is searched until you click the map.',
          'The data comes from a community feed (adsb.lol) and needs the internet. It shows only aircraft that broadcast ADS-B, so some will be missing. It is not an airspace authorization.',
          'Everyone who can sign in can use the page.',
        ],
      },
      {
        id: 'radius-and-refresh',
        title: 'Radius, refresh and colors',
        summary: 'Set how wide to look and how often to update, and read the colors to see which aircraft are near drone height.',
        steps: [
          'Pick **Radius**: 25, 50, 100, 150 or 200 miles.',
          'Pick **Refresh**: every 5, 10, 15 or 30 seconds, or **Off**.',
          'Choose **Refresh** (the button) to update right now.',
          'Use the **Altitude** key at the bottom right of the map. Red is below 400 ft, orange is 400 to 1,000 ft, yellow is 1,000 to 5,000 ft, blue is 5,000 to 15,000 ft, and grey is higher or unknown.',
        ],
        notes: [
          'Your radius and refresh choices are remembered on this device.',
          'After you pick a point, a **Recent** button shows that point\'s coordinates. Choose it to jump back to your last pick.',
          'If an automatic update fails, nothing pops up and the old aircraft stay on the map. A manual **Refresh** shows an error.',
          '(cached) next to the count means the answer was reused from a few moments ago.',
        ],
      },
    ]
  },
  {
    id: 'flight-plans',
    title: 'Flight Plans',
    topics: [
      {
        id: 'overview',
        title: 'The flight plans list',
        summary: 'A flight plan is a request to fly, sent to a supervisor for approval before the flight. The Flight Plans page lists every plan and where it stands.',
        steps: [
          'Choose **Flight Plans** in the sidebar. A number on the sidebar item counts plans waiting for review.',
          'Choose **All Plans** to see everyone\'s plans, or **My Plans** to see only those you submitted.',
          'Use the **All Statuses** list to show only Pending, Approved, Denied, Cancelled or Completed plans.',
          'Click a row, or the arrow at its right, to open the details: description, case number, height, length, checklist, review notes, and who submitted it.',
          'Choose **Export CSV** to download the list as a CSV file, a plain table that opens in a spreadsheet.',
        ],
        notes: [
          'A badge with a number and the word **Pending** shows how many plans wait for a decision.',
          'Everyone can see the list. Supervisors and pilots can submit plans by default. Viewers cannot.',
          'The **Weather Briefing** link in the details opens the National Weather Service site in a new tab. For the full briefing, use the **Weather** page.',
        ],
      },
      {
        id: 'submitting',
        title: 'Submitting a plan',
        summary: 'Submit a plan before you fly, so a supervisor can approve it.',
        image: {
          src: '/manual/flight-plans-submitting.png',
          alt: 'The Submit Flight Plan form with title, date, pilot, vehicle, location and other fields',
          caption: 'The Submit Flight Plan form.',
        },
        steps: [
          'Choose **Submit Plan** on the Flight Plans page.',
          'Fill in the required fields marked with a star: **Title**, **Planned Date/Time** and **Pilot**.',
          'Add what you know: **Vehicle**, **Location**, **Latitude**, **Longitude**, **Purpose**, **Case Number** and **Description**.',
          'Enter **Max Altitude (ft)** and **Est. Duration (min)**.',
          'Tick **Pre-flight checklist completed** if you have done the checklist.',
          'Add **Notes** if needed, then choose **Submit Plan**.',
        ],
        notes: [
          'The planned height must be between 0 and 400 feet above the ground. Higher is refused.',
          'If your account is linked to a pilot, that pilot is filled in for you.',
          'The checklist tick is only a statement. It does not look up a checklist on the **Checklists** page.',
          'New plans start as **pending**.',
        ],
      },
      {
        id: 'reviewing',
        title: 'Approving or denying a plan',
        summary: 'A reviewer decides each pending plan. Nobody can approve or deny a plan they submitted themselves, so a second person always makes the call.',
        image: {
          src: '/manual/flight-plans-reviewing.png',
          alt: 'The flight plans table with a pending plan and an approved plan and their action buttons',
          caption: 'The plans table. A pending plan shows approve and deny buttons to a reviewer.',
        },
        steps: [
          'Find a plan marked **pending**. Open its details to read it.',
          'To approve, choose the check mark, then **Approve** in the box that opens.',
          'To deny, choose the ban mark. In **Deny Flight Plan**, type a **Denial Reason** (required) and optional **Review Notes**, then choose **Deny Plan**.',
          'Read the result in the details: who reviewed it, when, and the notes.',
        ],
        notes: [
          'Supervisors and admins can approve, deny and delete plans by default. Pilots and viewers cannot.',
          'The approve and deny buttons do not show on a plan you submitted, even if you are an admin. Ask someone else.',
          'Only a pending plan can be approved or denied.',
          'An admin can change who may review under **Settings**.',
        ],
      },
      {
        id: 'editing-and-cancelling',
        title: 'Editing, cancelling and reopening',
        summary: 'Change a plan when the details change, cancel one you will not fly, or put a closed plan back in the queue.',
        steps: [
          'To edit, choose the pencil on the plan. **Edit Flight Plan** opens with the same fields, plus **Linked Flight ID** for the flight flown under the plan. Choose **Save Changes**.',
          'To cancel, choose the cross mark on a pending or approved plan and confirm.',
          'To reopen, an admin chooses the circular arrow on a denied or cancelled plan and confirms. It goes back to pending.',
          'To delete, a reviewer chooses the cross at the end of the row and confirms.',
        ],
        notes: [
          'Supervisors can edit any plan. Pilots can edit only plans they submitted. Both can edit pending and denied plans. Only an admin can edit an approved, cancelled or completed plan.',
          'If you change a reviewed detail on an approved or denied plan, such as the date, pilot, place or height, the plan goes back to pending and the earlier decision is cleared. Changing only the notes or the linked flight does not.',
          'Cancel needs the same permission as edit.',
          'Delete cannot be undone. Cancel instead if you want to keep the record.',
        ],
      },
    ]
  },
  {
    id: 'checklists',
    title: 'Checklists',
    topics: [
      {
        id: 'completing',
        title: 'Completing a pre-flight checklist',
        summary: 'Run a checklist before a flight and save the result as a record. Each submitted checklist is kept for compliance.',
        image: {
          src: '/manual/checklists-completing.png',
          alt: 'The Complete Pre-Flight Checklist dialog with a template chosen and some items ticked',
          caption: 'The Complete Pre-Flight Checklist dialog with two of four items ticked. The button changes to Submit as not passed because required items are open.',
        },
        steps: [
          'Choose **Checklists** in the sidebar, then **Complete Checklist**.',
          'Pick a **Template** and a **Pilot**. Pick a **Vehicle** if the checklist is for one drone.',
          'Tick each item as you check it. Add a short note beside an item if needed.',
          'Add **Overall Notes** if you want.',
          'Choose **Submit Checklist**.',
        ],
        notes: [
          'A star beside an item means it is required.',
          'If a required item is not ticked, a warning shows and the button changes to **Submit as not passed**. You can still submit, and the result is saved as not passed.',
          'Supervisors, pilots and admins can complete checklists by default. Viewers cannot.',
          'The **Pilot** list is not limited to you. Choose the pilot who did the check.',
        ],
      },
      {
        id: 'completions',
        title: 'Finding past checklists',
        summary: 'The Completions tab is the history of every submitted checklist.',
        steps: [
          'Choose the **Completions** tab.',
          'Read the date, pilot, vehicle and template, and a green tick or red cross under **Passed**.',
          'Choose the eye icon to open **Checklist Details**. It shows each item, ticked or not, with its notes. A badge says **All Passed** or **Items Failed**.',
          'Choose **Export CSV** to download the history as a CSV file, a plain table that opens in a spreadsheet.',
        ],
        notes: [
          'Supervisors and admins can delete a checklist from its details with **Delete**. This cannot be undone. Do it only for a checklist entered by mistake.',
          'Everyone can read past checklists by default.',
        ],
      },
      {
        id: 'templates',
        title: 'Building and managing templates',
        summary: 'A template is the list of items a checklist asks for. Supervisors and admins build them, and everyone completes them.',
        image: {
          src: '/manual/checklists-templates.png',
          alt: 'The Create Checklist Template dialog with a name, description and a list of items',
          caption: 'The Create Checklist Template dialog.',
        },
        steps: [
          'On the **Templates** tab, choose **Create Template**.',
          'Type a **Name** and an optional **Description**.',
          'Pick a **Vehicle Model** to label the template for one model, or leave **All models**.',
          'Type each item under **Checklist Items**. Untick **Required** for an item that is nice to have. Use the arrows to reorder and the bin to remove.',
          'Choose **Add Item** for more rows, then **Create Template**.',
          'To change one later, choose the pencil on its card, then **Update Template**.',
        ],
        notes: [
          'You need a name and at least one item.',
          'The vehicle model is a label. It does not stop anyone using the template with another drone.',
          'A template that has been used cannot be deleted, because submitted checklists keep a link to it. Edit it and untick **Active** instead. It then drops off the list and is no longer offered.',
          'Supervisors and admins can manage templates by default. Pilots and viewers see them but have no **Create Template** button.',
        ],
      },
    ]
  },
  {
    id: 'alerts',
    title: 'Alerts',
    topics: [
      {
        id: 'overview',
        title: 'Reading the alerts list',
        summary: 'Alerts are notices the app raises on its own when something needs attention. Today the app raises an alert for each maintenance schedule that is due or overdue.',
        steps: [
          'Choose **Alerts** in the sidebar.',
          'Read each card: its title, a severity badge (info, warning or critical), the message and the time.',
          'A blue dot marks an alert nobody has marked as read. Read alerts are faded.',
          'Use the **All Severities** list to show only Info, Warning or Critical alerts.',
          'The count at the top, such as 3 total alerts, counts everything not dismissed.',
        ],
        notes: [
          'Overdue maintenance alerts are checked once a day, early in the morning. They are warnings.',
          'When the schedule is completed or moved to a later date, its alert goes away by itself. A new alert starts if it becomes overdue again.',
          'Each schedule has one open alert at a time.',
          'The page shows up to 100 alerts, newest first. Everyone can read them by default.',
          'When there is nothing to show, the page says **No alerts found**.',
        ],
      },
      {
        id: 'dismissing',
        title: 'Marking read and dismissing',
        summary: 'Clear alerts you have dealt with so the list shows only what is left.',
        steps: [
          'To mark one as read, choose the check mark on its card.',
          'To remove one, choose the cross on its card.',
          'To remove all of them, choose **Dismiss All**, then confirm in **Dismiss All Alerts**.',
        ],
        notes: [
          'Alerts are shared. When anyone marks one read or dismisses it, it changes for everyone.',
          'Supervisors and admins can mark read and dismiss by default. Pilots and viewers can read the list but do not see these buttons.',
          '**Dismiss All** removes every alert, not only the ones on your screen after a severity filter. Think before you use it.',
          'Dismissing an alert does not fix the maintenance. If it is still overdue, check **Maintenance**.',
        ],
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
        title: 'The compliance dashboard',
        summary: 'The **Compliance** page shows how well the unit is keeping up with its paperwork and upkeep, as one score out of 100 with the problems behind it.',
        image: {
          src: '/manual/compliance-compliance-score.png',
          alt: 'The Compliance Dashboard with a score circle and coloured cards for expired certifications, registrations, maintenance and incidents',
          caption: 'The compliance score and the cards behind it.',
        },
        steps: [
          'Open **Compliance** in the sidebar.',
          'Read the **Compliance Score**. It is green above 80, amber above 60 and red at 60 or below.',
          'Click any card (for example **Expired Certs**, **Expired Registrations**, **Overdue Maintenance** or **Open Incidents**) to go to the page where you fix it.',
          'The summary bar shows **Active Pilots**, **Active Vehicles**, **Cert Compliance**, **Reg Compliance** and **Currency Compliance**.',
          'Click **Refresh** to reload the numbers.',
        ],
        notes: [
          'Everyone can open this page. The names in the lists follow what you may view, so a role without certification access sees the counts but not the pilot names.',
          'The score starts at 100 and loses points for: expired certifications (up to 25), expired FAA registrations (up to 20), overdue maintenance (5 each, up to 20), open or investigating incidents (10 each, up to 20), pilots out of currency (up to 15), and operating authorities that are expiring or expired.',
          'Currency counts only when at least one active currency rule exists. With no rules **Currency Compliance** shows a dash.',
          'Only active pilots and active vehicles are counted.',
          'An expired operating authority that grounds the unit caps the score at 50, and the reason shows under the score. See **Operating Authority**.',
          '**Export checkouts CSV** downloads the equipment checkout log (it needs report export and fleet access). **Generate Compliance Report** opens **Reports** for people who may generate reports.',
        ],
      },
      {
        id: 'attention-items',
        title: 'Items requiring attention',
        summary: 'The list at the bottom of the **Compliance** page puts every open problem in one place, worst first.',
        steps: [
          'Scroll to **Items Requiring Attention**. The number on the right says how many items there are.',
          'Each line has a severity badge, a description and sometimes a count.',
          'Click a line to open the page that deals with it.',
        ],
        notes: [
          'The order is: grounding authority, critical (expired certifications, expired registrations, other expired authorities), high, medium, low.',
          'Lines cover expiring certifications, expiring authorities, overdue maintenance, open incidents, unreviewed flights, pending flight plans and pilots out of currency or close to it.',
          'When the list is empty the page says **All Clear**.',
        ],
      },
      {
        id: 'currency-reminders',
        title: 'Pilot currency and reminders',
        summary: 'The **Pilot Currency Status** section shows who is lapsed or close to lapsing, and lets a supervisor email them a reminder.',
        steps: [
          'Scroll to **Pilot Currency Status**. The header shows how many pilots are lapsed out of the total.',
          'Use the list to choose **Lapsed + Expiring 30d**, **Lapsed only** or **All pilots**.',
          'Each row has a badge: **LAPSED**, the days left (amber within 14 days, blue within 30) or **CURRENT**, plus how many hours and flights the pilot has against each rule. Click a row to open the pilot.',
          'Click **Show all** to see more than the first eight rows.',
          'To email lapsed pilots, click **Send Reminders**, add an optional **Message to pilots (optional)**, and click **Send**.',
        ],
        notes: [
          '**Send Reminders** is for supervisors and admins by default. It emails every lapsed pilot who has an email address on file. The result message tells you how many were sent, skipped for no email, or failed. The unit needs email set up first (see **Settings**).',
          'A row shows **no email** when the pilot has no address, or when you do not have contact access.',
          'With no currency rules the section says **No currency rules defined** and offers **Open Settings**. See Pilot currency to add one.',
        ],
      },
    ]
  },
  {
    id: 'operating-authority',
    title: 'Operating Authority',
    topics: [
      {
        id: 'operating-authority',
        title: 'Operating authority',
        summary: 'The **Operating Authority** page tracks the unit\'s own COAs (certificates of authorization) and Part 107 waivers: when they were issued, when they expire, and the paperwork behind them.',
        image: {
          src: '/manual/operating-authority-operating-authority.png',
          alt: 'The Add Operating Authority dialog with type, title, number, issue and expiry dates, record status and the Expiry grounds the unit box',
          caption: 'The Add Operating Authority dialog.',
        },
        steps: [
          'Open **Operating Authority** in the sidebar. The table lists **Authority**, **Type**, **Issued**, **Expires**, **Status** and **Documents**.',
          'To add one, click **Add Authority**.',
          'Pick the **Type** (COA or Part 107 Waiver) and enter a **Title**. Add the **COA / waiver number**, **Issue date** and **Expiry date**.',
          'Leave **Record status** on **Active**. Tick or untick **Expiry grounds the unit** (see below). Add **Notes** if useful.',
          'Click **Save**.',
          'Use the page icon on a row to attach or view documents, the pencil to edit and the bin to delete.',
        ],
        notes: [
          'Everyone who may view it can read the page. Supervisors and admins can add, edit and delete by default. An admin can change this under **Settings**.',
          'The badge shows **Active**, **Expires in** a number of days (within 90 days) or **Expired**. Records with no expiry date never expire.',
          '**Expiry grounds the unit** should be on for an authority the unit flies under. Turn it off for one whose lapse limits one kind of operation, such as a night waiver.',
          'An authority within 90 days of expiry takes 5 points off the compliance score. An expired one that grounds the unit caps the score at 50, with the reason under the score, because a green score while the unit is unauthorized would mislead. An expired one that does not ground the unit takes 10 points off.',
          'Set **Record status** to **Superseded** (a newer authority replaced it) or **Not applicable** (the unit no longer uses it) to keep the record on file for reports without it counting against compliance. Deleting removes it for good.',
          'With no authorities on file the score is unaffected.',
          'Authorities held during the period appear in the Annual Unit Report and the Certifications report.',
        ],
      },
    ]
  },
  {
    id: 'incidents',
    title: 'Activity Reports (Incidents)',
    topics: [
      {
        id: 'incident-reporting',
        title: 'Reporting an incident or a success',
        summary: 'Use **Activity Reports** to record something that went wrong (a crash, near miss or equipment failure) or something that went well (a missing person found, evidence collected).',
        image: {
          src: '/manual/incidents-incident-reporting.png',
          alt: 'The Report Incident dialog with the Incident and Success switch, date, severity, title, category, description, pilot and vehicle filled in with demo data',
          caption: 'The Report Incident dialog.',
        },
        steps: [
          'Open **Activity Reports** in the sidebar and click **New Report**.',
          'Choose **Incident** or **Success** at the top of the dialog.',
          'Fill in the **Date**, then the **Severity** (Minor, Moderate, Major or Critical). For a success, pick an **Impact Level** instead.',
          'Enter a **Title** and a **Description**. Both are required. Pick a **Category** and add a **Location**.',
          'Link a **Pilot**, **Vehicle** or **Linked Flight** if it applies.',
          'For an incident, add a **Damage Description**, **Estimated Cost ($)** and tick **Equipment Grounded** if the aircraft or gear is out of service. For a success, add an **Outcome Description**.',
          'Click **Report Incident** (or **Report Success**).',
        ],
        notes: [
          'Supervisors and pilots can create reports. Viewers can only read them.',
          'Incident categories are Crash, Near Miss, Equipment Failure, Injury, Airspace Violation and Other. Success categories are Missing Person Found, Suspect Located, Evidence Collected, Community Event, Training Success and Other Success.',
          '**Linked Flight** lists flights only for people who may view flights.',
          'A new report starts as **open**. Open and investigating incidents lower the compliance score.',
        ],
      },
      {
        id: 'reviewing-reports',
        title: 'Reading and filtering reports',
        summary: 'Find a past report, or see what is still open.',
        steps: [
          'At the top, the cards show **Open**, **Investigating**, **Resolved** and **Total**.',
          'Click **All**, **Incidents** or **Successes** to choose the kind of report.',
          'Use **All Statuses**, **All Severities** and **All Categories** to narrow the table.',
          'Click a row, or the arrow in **Actions**, to open its details: description, location, damage, cost, resolution, corrective actions, notes, who reported it and the linked flight.',
          'Photos linked to the report show at the bottom of its details.',
        ],
        notes: [
          '**Export CSV** downloads the list. It needs the permission to export reports.',
          'Attaching photos to a report needs file access with custody rights. Supervisors and admins have it by default.',
        ],
      },
      {
        id: 'resolving-incidents',
        title: 'Resolving and deleting reports',
        summary: 'Close the loop on an incident by recording what happened and what you changed.',
        steps: [
          'On the report\'s row, click the check mark (**Resolve**).',
          'Choose the **Status**: **Investigating**, **Resolved** or **Closed**.',
          'Fill in **Resolution**, **Corrective Actions** and **Resolution Date** (it starts as today).',
          'Click **Update**.',
        ],
        notes: [
          'Resolving and deleting are for supervisors and admins by default. The check mark is hidden once a report is **closed**.',
          'Deleting asks you to confirm and cannot be undone.',
          'An admin can change who may create, edit, resolve or delete reports under **Settings**.',
        ],
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
