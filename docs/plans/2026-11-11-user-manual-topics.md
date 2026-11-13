# User Manual Topics View and Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the in-app manual a Topics view (menu plus one topic) and a One page view chosen at the top, rewrite every topic in plain language against the current app, and add cropped pictures made from fake data.

**Architecture:** Manual content moves out of `UserManualPage.jsx` into a data module of sections and topics. Small pure helpers flatten, find, page through and search topics. Two layout components render the same data; the page owns the view switch (remembered in browser storage), the search box and the `?topic=` address. Pictures are PNG files in `frontend/public/manual/`, produced by a separate Playwright run against the local e2e backend seeded with fake demo data.

**Tech Stack:** React 19, react-router-dom 7, Tailwind 4, vitest with Testing Library, Playwright.

**Spec:** `docs/specs/2026-11-11-user-manual-topics-design.md`

## Global Constraints

- Branch `fix/login-lockout-per-ip` (PR 99). Do not merge; the owner merges once the manual is finished.
- Commits: one-line imperative subject, author `git -c user.name=JonGaydos -c user.email=108827725+JonGaydos@users.noreply.github.com commit`, no AI attribution lines.
- User-facing text: second person, short sentences, no em dashes, page and button names in `**bold**` exactly as the app shows them.
- No unexplained technical terms (JWT, endpoint, SQLite, CORS, cron, JSON). CSV, PDF, API token and SMTP get a short plain explanation the first time they appear.
- Every role sees every topic; role limits are stated in plain words ("Admins only", "Supervisors and admins by default").
- Colors come from theme tokens (`bg-card`, `border-border`, `text-muted-foreground`, `bg-secondary`, `bg-accent`, `text-primary`), never fixed colors.
- View storage key `dum.manual.view`, values `topics` or `page`, default `topics`. Topic address `?topic=<sectionId>.<topicId>`.
- Phone layout below 768 px (Tailwind `md`).
- Pictures: no real data of any kind (names, emails, phones, serials, registrations, addresses, map locations). Fake data only.
- Source of truth for content is the code on this branch and the default permission grid in `backend/app/services/permissions.py`. Staging (192.168.0.100:3015) only for spot checks. Never production.

## Review Focus

- A `?topic=` address for a topic that exists opens it even if the search box later hides it; typing a search that does not match it opens the first match instead.
- A search that matches nothing in Topics view shows "No topics match your search." with no Previous/Next and no crash.
- Browser storage that throws (private mode, blocked storage) still renders the page in Topics view, and switching views still works for the session.
- The phone topic list closes on selection, on Escape and on a tap outside.
- A topic picture that is missing from `public/manual/` is caught by a test before release, and every picture has alt text.

---

### Task 1: Content module and topic helpers

**Files:**
- Create: `frontend/src/pages/manual/content.js`
- Create: `frontend/src/pages/manual/topics.js`
- Create: `frontend/src/pages/manual/topics.test.js`
- Create: `frontend/src/pages/manual/ManualText.jsx`
- Modify: `frontend/src/pages/UserManualPage.jsx` (import `sections` from the module; behavior unchanged in this task)

**Interfaces:**
- Produces: `content.js` exports `sections: Section[]` where `Section = { id: string, title: string, topics: Topic[] }` and `Topic = { id: string, title: string, summary: string, steps?: string[], notes?: string[], image?: { src: string, alt: string, caption: string } }`. `summary` may hold several lines using today's bullet (`• `) and numbered (`1.`) conventions.
- Produces: `topics.js` exports
  - `topicKey(sectionId, topicId) => string` (`"flights.adding-a-flight"`)
  - `flattenTopics(sections) => Array<{ key, section, topic }>` in manual order
  - `findTopic(sections, key) => { key, section, topic } | null`
  - `neighbors(sections, key) => { prev: entry | null, next: entry | null }`
  - `topicText(topic) => string` (title, summary, steps and notes joined, lower case)
  - `filterSections(sections, query) => Section[]` (sections keep only topics whose `topicText` or section title contains the trimmed, lower-cased query; empty query returns `sections`)
- Produces: `ManualText({ text })` renders one string: lines starting `• ` as bullets, `1.` lines as numbered lines, blank lines as gaps, and `**x**` anywhere inside a line as `<strong>`.

- [ ] **Step 1: Write the failing tests** in `topics.test.js` against a small inline fixture of two sections with three topics:
  - `flattenTopics` returns keys in order `['a.one', 'a.two', 'b.three']`.
  - `findTopic(fixture, 'b.three').topic.title === 'Three'`; `findTopic(fixture, 'x.y') === null`.
  - `neighbors(fixture, 'a.one')` has `prev === null`, `next.key === 'a.two'`; `neighbors(fixture, 'b.three').next === null`.
  - `filterSections(fixture, '  STEP  ')` keeps only the topic whose `steps` contain "step" and drops the empty section.
  - `filterSections(fixture, '')` returns the fixture unchanged.
- [ ] **Step 2: Run** `npx vitest run src/pages/manual/topics.test.js`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement `topics.js`.**
- [ ] **Step 4: Port today's content into `content.js`.** Each current section becomes a `Section` with the same `id` and `title`; each current `content` entry becomes a `Topic` with `id` = slug of its title, the same `title`, and `summary` = its old `body`. Move `renderMarkdown` into `ManualText.jsx` and add inline `**bold**` support.
- [ ] **Step 5: Point `UserManualPage.jsx` at the module** (render `topic.summary` through `ManualText`). Run `npx vitest run src/pages` . Expected: PASS, including the existing `UserManualPage.test.jsx`.
- [ ] **Step 6: Commit** `Move manual content into its own module`.

### Task 2: Topic view and Topics layout

**Files:**
- Create: `frontend/src/pages/manual/TopicView.jsx`
- Create: `frontend/src/pages/manual/TopicsLayout.jsx`
- Create: `frontend/src/pages/manual/TopicsLayout.test.jsx`

**Interfaces:**
- Consumes: `flattenTopics`, `neighbors`, `ManualText` from Task 1.
- Produces: `TopicView({ section, topic })`: section name as a small label, topic title as `h2`, `summary` via `ManualText`, `steps` as an ordered list under an `h3` "Steps", `notes` as a list under an `h3` "Good to know", and `image` as `<figure>` with `<img src alt loading="lazy">` and `<figcaption>`.
- Produces: `TopicsLayout({ sections, currentKey, onSelect })`. `sections` is already filtered. Renders:
  - From `md` up: a `nav` labelled "Manual topics", about 240 px, sticky, listing sections as toggle buttons (the current topic's section open) and topics as buttons with `aria-current="page"` on the current one; the topic area with `TopicView` and Previous/Next buttons labelled with the neighbor titles (`← <title>`, `<title> →`).
  - Below `md`: a button showing `<Section> › <Topic>` with `aria-expanded`; when open, the same topic list in a panel. Selecting a topic calls `onSelect` and closes the panel; Escape and a click outside close it.
  - When `sections` is empty: the text "No topics match your search." and no Previous/Next.

- [ ] **Step 1: Write the failing tests** in `TopicsLayout.test.jsx` (render with a two-section fixture):
  - shows only the current topic's title as `h2` and not the other topics' summaries.
  - clicking a topic button in the menu calls `onSelect('b.three')`.
  - Next button text contains the next topic's title; clicking it calls `onSelect` with its key; no Previous on the first topic.
  - the topic picker button has `aria-expanded="false"`; clicking it sets `true` and shows the list; choosing a topic closes it; pressing Escape closes it; a click on `document.body` outside the panel closes it.
  - with `sections=[]` shows "No topics match your search." and no buttons named Previous or Next.
  - a topic with `image` renders an `img` with the given `alt` and `loading="lazy"`, and the caption text.
- [ ] **Step 2: Run** `npx vitest run src/pages/manual/TopicsLayout.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement `TopicView.jsx` and `TopicsLayout.jsx`.** Use `hidden md:flex` / `md:hidden` for the two layouts so both exist in the DOM; tests query by role within the matching container.
- [ ] **Step 4: Run the test.** Expected: PASS.
- [ ] **Step 5: Commit** `Add the manual Topics layout`.

### Task 3: One page layout, view switch, address and search

**Files:**
- Create: `frontend/src/pages/manual/OnePageLayout.jsx`
- Modify: `frontend/src/pages/UserManualPage.jsx`
- Modify: `frontend/src/pages/UserManualPage.test.jsx`
- Create: `frontend/src/pages/manual/content.test.js`
- Create: `frontend/e2e/manual.spec.js`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: `OnePageLayout({ sections })`: today's collapsible section cards, every topic shown through `TopicView`, sections start expanded.
- Produces: `UserManualPage` header row: title, subtitle "How to use Drone Unit Manager", and a two-button group (`role="group"`, `aria-label="Manual layout"`) with buttons "Topics" and "One page" (`aria-pressed`). Search placeholder "Search the manual...".
  - View: read `dum.manual.view` once inside `try/catch` (fallback `topics`); write it on change inside `try/catch`.
  - Address: `useSearchParams`. In Topics view the current key comes from `topic`; a missing or unknown key falls back to the first topic of the filtered list. Selecting a topic sets `topic` (push). Arriving with a valid `topic` while the stored view is `page` switches to `topics` and stores it. One page view removes `topic`.
  - Search: filters with `filterSections`; in Topics view, when the current topic is not in the filtered list, the first filtered topic is shown (address updated with replace).

- [ ] **Step 1: Rewrite `UserManualPage.test.jsx`.** Keep the heading and search tests updated to the new placeholder and view, and add:
  - default view is Topics: the first topic's title is the only `h2`.
  - clicking "One page" shows several sections' titles and stores `page` in `dum.manual.view`; re-rendering starts in One page.
  - `route: '/manual?topic=flights.<an existing topic id>'` opens that topic in Topics view even when `dum.manual.view` is `page`.
  - `route: '/manual?topic=nope.nope'` shows the first topic.
  - typing a word found only in one topic's text shows that topic.
  - typing `zzzznotathing` shows "No topics match your search."
  - in One page view, typing a section-specific word hides the other sections' titles.
  - with `localStorage.getItem` mocked to throw, the page renders in Topics view and "One page" still switches.
- [ ] **Step 2: Write `content.test.js`:** section ids unique; topic ids unique within a section; every topic has a non-empty `title` and `summary`; no `—` in any title, summary, step, note, alt or caption; every `image.src` starts with `/manual/` and the file exists under `frontend/public` (use `node:fs` and `node:path`); every image has non-empty `alt` and `caption`.
- [ ] **Step 3: Run** `npx vitest run src/pages`. Expected: FAIL on the new page tests (content test may pass).
- [ ] **Step 4: Implement `OnePageLayout.jsx` and the page changes.**
- [ ] **Step 5: Run** `npx vitest run src/pages`. Expected: PASS.
- [ ] **Step 6: Write `e2e/manual.spec.js`:** open `/manual`, click a topic in the "Manual topics" menu, expect its `h2`; click "One page", expect at least three section titles visible; reload, still One page. Run `npx playwright test e2e/manual.spec.js` (needs `backend/.venv` or the venv candidate added in Task 4). Expected: PASS.
- [ ] **Step 7: Run** `npm run lint` and `npm run build`. Expected: no errors.
- [ ] **Step 8: Commit** `Add the manual Topics and One page views`.

### Task 4: Picture tooling with fake demo data

**Files:**
- Modify: `frontend/e2e/start-backend.mjs` (add `backend/venv` to the Python candidates, after `.venv`)
- Create: `frontend/playwright.manual.config.js`
- Create: `frontend/manual-shots/seed-demo.js`
- Create: `frontend/manual-shots/shots.js`
- Create: `frontend/manual-shots/shots.spec.js`
- Create: `frontend/manual-shots/README.md`
- Modify: `frontend/package.json` (script `"manual:shots": "playwright test -c playwright.manual.config.js"`)
- Modify: `frontend/.gitignore` if needed so `public/manual/*.png` is tracked

**Interfaces:**
- Consumes: `e2e/global-setup.js`, `e2e/start-backend.mjs`, `e2e/helpers/seed.js` (`apiLogin`, `api`, `create*`).
- Produces: `playwright.manual.config.js`: same `webServer` and `globalSetup` as `playwright.config.js`, `testDir: 'manual-shots'`, viewport 1280x800, `deviceScaleFactor: 1`, admin `storageState`, theme left at the app default (Sandstone).
- Produces: `seed-demo.js` exports `seedDemo(request, adminToken)`: idempotent (skips when a pilot named "Avery Brooks" exists), creates only fake records: at least 6 pilots with made-up names (Avery Brooks, Jordan Ellis, Sam Ortega, Riley Chen, Morgan Patel, Casey Nguyen), `@example.com` emails and `555-01xx` phones; 3 vehicles with serials `DEMO-0001`.. and fake registrations `FA-DEMO-01`..; batteries, controllers, docks, sensors where the API allows; 20 flights over the last 60 days with locations limited to the text "Training Field A" and "Riverside Park" and no coordinates; certification types and assignments with a mix of current, expiring and expired; one maintenance record and schedule each; one incident; one pending and one approved flight plan; one mission and one training log; one calendar event; one folder with one small text document.
- Produces: `shots.js` exports `SHOTS: Array<{ file: string, route: string, prepare?: (page) => Promise<void>, target: (page) => Locator }>`. `shots.spec.js` runs `seedDemo` once, then for each entry navigates, runs `prepare`, waits for network idle, and saves `target(page).screenshot()` to `public/manual/<file>`. Entries are added by the content tasks.

- [ ] **Step 1: Add one starter entry** to `SHOTS`: `manual-layout-switch.png` at `/manual`, target the "Manual layout" group's parent header row.
- [ ] **Step 2: Run** `npm run manual:shots`. Expected: PASS, `public/manual/manual-layout-switch.png` exists.
- [ ] **Step 3: Open the picture and check by eye** that it shows the header and switch and no real data.
- [ ] **Step 4: Write `manual-shots/README.md`:** what the run does, `npm run manual:shots`, that it uses a fresh local database with fake data only, and that pictures are checked by eye before commit.
- [ ] **Step 5: Run** `npx playwright test` (normal e2e). Expected: unchanged results; the manual-shots folder is not picked up.
- [ ] **Step 6: Commit** `Add the manual picture tooling with fake demo data`.

### Tasks 5 to 10: Content rewrite by area

Each of these tasks has the same steps; only the area changes.

**Files (each task):**
- Modify: `frontend/src/pages/manual/content.js` (the sections listed)
- Modify: `frontend/manual-shots/shots.js` (entries for that area)
- Modify: `frontend/manual-shots/seed-demo.js` (only if a picture needs more fake data)
- Create: `frontend/public/manual/<area>-*.png`

**Interfaces:**
- Consumes: `Topic` shape (Task 1), `SHOTS` and `seedDemo` (Task 4).

**Areas:**
- **Task 5: Getting started and the basics.** First sign-in and setup (`SetupPage`, `LoginPage`), roles and the permission grid (`backend/app/services/permissions.py`, Settings permissions screen), signing in, sessions, the idle lock and the login lock (10 failures from one address lock that address out for 15 minutes; 50 across all addresses lock the account; signing in successfully clears it), navigating the app and the sidebar, themes, command palette, cross-reference links, dates and times.
- **Task 6: Daily operations.** Dashboard, Analytics, Calendar, Weather, Airspace, Flight Plans (submit, approve, deny, full editing, nobody approves or denies their own plan), Checklists, Alerts.
- **Task 7: Flights and logs.** Flights list, filters and paging, adding a flight by hand, reviewing, Flight detail (map and telemetry), Mission Log, Training Log, CSV export and import of flights where the UI offers it.
- **Task 8: Fleet.** Fleet page, vehicles, batteries and battery health, controllers, docks, sensors, other equipment, components, registrations, fleet health, drone locations, equipment checkouts, merging duplicates.
- **Task 9: Pilots and compliance.** Pilots and pilot detail, currency rules, needs attention, certifications (matrix, assigning, editing including clearing fields and notes, renewing, history), compliance, operating authorities, incidents.
- **Task 10: Records, reports and administration.** Maintenance and schedules, Documents (folders, upload, recently deleted), Media and photos, Reports and exports, Integrations (Skydio connect, sync, disconnect), Audit Log, Settings (general, users, permissions, Email Digest card, SMTP, API tokens, backup and restore: backups hold everything including passwords and keys and must be stored like passwords; restoring onto a running install needs `REPLACE ALL DATA` typed and signs everyone out; a fresh install restores from the setup screen with the install token). Geofences are gone and are not mentioned.

**Steps (each task):**
- [ ] **Step 1: Inventory.** Read each page in the area (`frontend/src/pages/*Page.jsx` and the components they import) and the matching permission keys. Write a short scratch list per page: what a user sees, every button and field label, what each role can do by default.
- [ ] **Step 2: Rewrite the area's topics** in `content.js` from the inventory, using `steps` and `notes`, not from the old text. Remove old topics that describe things that no longer exist.
- [ ] **Step 3: Check labels.** For every `**Label**` in the new text, grep the source for the exact label. Expected: each one found in a page or component of that area.
- [ ] **Step 4: Add `SHOTS` entries** for topics where a picture helps (a dialog, card or toolbar), file names `<area>-<topic-id>.png`, and set each topic's `image` with alt text and a one-line caption.
- [ ] **Step 5: Run** `npm run manual:shots`. Expected: PASS; the new files exist.
- [ ] **Step 6: Check every new picture by eye** for real data and for showing what the caption says. Any picture that needs data the local demo cannot provide (for example a flight track on the map) is left out of `SHOTS`, its topic keeps no `image`, and it is listed for Task 11.
- [ ] **Step 7: Run** `npx vitest run src/pages`. Expected: PASS, including `content.test.js`.
- [ ] **Step 8: Commit** `Rewrite the <area> manual topics in plain language`.

### Task 11: Remaining pictures, the old Markdown manual, and final checks

**Files:**
- Delete: `docs/USER_MANUAL.md`
- Modify: any file that links to `docs/USER_MANUAL.md` (none found on 2026-11-11 outside specs and plans; recheck)
- Modify: `frontend/src/pages/manual/content.js` and `frontend/public/manual/` for staging pictures, if any

- [ ] **Step 1: Delete `docs/USER_MANUAL.md`** (`git rm`). Grep the repo (excluding `node_modules`, `docs/specs`, `docs/plans`) for `USER_MANUAL`; point any hit to the in-app manual (**User Manual** in the sidebar, address `/manual`).
- [ ] **Step 2: Staging pictures (only if Tasks 5 to 10 listed any).** Ask the owner before changing staging data. With approval: in the in-app browser with the owner signed in on 192.168.0.100:3015, rename the people, vehicles and places shown on those screens to fake values through the app, take the pictures, check them by eye, save them to `public/manual/`, and set the topics' `image`. Record what was changed on staging so it can be re-cloned from production.
- [ ] **Step 3: Run the full frontend checks:** `npx vitest run`, `npm run lint`, `npm run build`, `npx playwright test`. Expected: all pass (the known local-only Node 24 failure `DocumentStoragePage > uploads a general document with no folder selected` is not a regression).
- [ ] **Step 4: Run** `backend/venv/Scripts/python.exe -m pytest -q` in `backend`. Expected: PASS.
- [ ] **Step 5: Commit** `Remove the Markdown manual; the manual lives in the app`, push, and update PR 99's title to "Per-address login lock and a rewritten user manual" and its Summary and Test Plan to cover both.
