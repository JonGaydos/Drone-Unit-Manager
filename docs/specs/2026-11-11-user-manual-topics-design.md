# User Manual: Topics View and Plain-Language Rewrite: Design

Status: approved by owner. Date: 2026-11-11.

## Intent

People open the manual to look up one thing ("how do I add a flight by hand", "why can't I edit this certification"). Today the manual is one long page of collapsible sections, written over many releases, and parts of it no longer match the app after the 3.4.2 staging-test fixes (PRs 97 to 99). The owner wants:

1. A quick topic menu: pick a topic, read just that topic.
2. The current single long page kept as an option.
3. A switch at the top of the manual page to choose between them.
4. Every part of the app explained in simple terms, checked against the app as it is now.

## Goals

- A two-option switch, "Topics" and "One page", at the top of the manual page, on the title row.
- Topics view on a computer: a topic menu on the left; sections (Flights, Fleet, and so on) open to list their topics; choosing a topic shows only that topic on the right, with Previous and Next links at the bottom that follow manual order.
- Topics view on a phone (narrow screens): no side menu. A bar under the search box shows the current topic ("Flights > Adding a flight by hand"); tapping it opens the full topic list; choosing a topic closes the list.
- One page view: today's long page with collapsible sections, with the same switch and search.
- Search works in both views. In Topics view, typing narrows the menu to topics whose title or text match, and the first match opens.
- The manual covers every page and feature a user can reach, written for a non-technical unit member.
- Topics carry pictures of the part of the app they talk about, with a short caption.
- Every topic follows one shape: one line on when you would use it, numbered steps where there are steps, then "Good to know" bullets (limits, role rules, gotchas).

## Non-goals

- No backend or API changes. The manual stays static content in the frontend.
- No editing of the manual inside the app, no translations.
- No change to the app's own navigation sidebar.

## Anti-goals

The work has failed, even if the views work, if any of these is true:

- The manual names a button, page, field or menu that does not exist, or by a different label than the app shows.
- The manual says a role can do something the default permission grid does not allow, or the reverse.
- The manual describes behavior that changed in PRs 97 to 99 the old way (for example geofences, restore without the typed confirmation, backups without secrets, the login lock).
- Unexplained technical terms in user-facing text (JWT, endpoint, SQLite, CORS, cron, JSON). Terms a unit member meets in the app (CSV, PDF, API token, SMTP in the admin section) get a short plain explanation the first time.
- Topics view on a phone needs sideways scrolling, or the topic list cannot be closed.
- Search finds nothing for a word that is in a topic's text.
- Any picture shows real data: a real person's name, email or phone, a real vehicle serial or registration, a real address, or a real flight track or location. The repository is public.

## Decided by the owner

- Two views, chosen with a switch at the top of the manual page (2026-11-11, from mockups: computer Topics, computer One page, phone Topics, phone topic list).
- Mostly used for looking up a specific thing.
- Read through the entire app so everything is explained simply.
- Pictures in topics, and never real data in them. Staging data may be changed to fake names and locations to get the pictures (2026-11-11).
- One manual only: the in-app manual. `docs/USER_MANUAL.md` is replaced by a short pointer to it (2026-11-11).
- One merge at the end: the manual work is built on the PR 99 branch (`fix/login-lockout-per-ip`) and merges with it once the manual is finished (2026-11-11).

## Builder's calls made in this design

- The chosen view is remembered per device in browser storage. Default for a first visit: Topics.
- The selected topic is reflected in the page address (for example `/manual?topic=flights.adding-a-flight`), so a topic can be linked to and the browser Back button works. An unknown topic in the address falls back to the first topic.
- A topic link always opens Topics view on that topic, even on a device set to One page, and that becomes the remembered view. One page view puts nothing in the address.
- The phone layout applies below 768 px. From 768 px up the side menu shows; below 1024 px the app's own sidebar is already folded away, so the menu fits on tablets.
- All topics are shown to every role. Topics or steps limited to some roles say so in plain words ("Admins only", "Supervisors and admins by default"), because an admin can change the permission grid.
- Section order follows the app's sidebar order, then Settings and admin topics last.
- Wording style: second person ("you"), short sentences, button and page names in bold exactly as the app shows them, no em dashes.

## Content work

- Source of truth is the code on `main` after PR 99: each page in `frontend/src/pages/`, the components it uses, and the default permission grid. The builder reads every page, lists what a user can see and do there, and writes or rewrites the topics from that list, not from the old text.
- Spot-check labels and flows on staging (192.168.0.100:3015) where the code is unclear. Never production.
- Cover at least: first sign-in and setup, roles and permissions, sign-in and the login lock, dashboard, analytics, calendar, flights, flight plans, checklists, weather, airspace, fleet (vehicles, batteries, controllers, docks, sensors, other equipment, components, registrations, fleet health, locations, checkouts), mission and training logs, pilots, certifications, currency and compliance, maintenance and schedules, incidents, documents and media, alerts, reports and exports, operating authorities, integrations (Skydio), audit log, settings (general, users, permissions, email digests, API tokens, SMTP, backup and restore), command palette, themes.
- Changes from PRs 97 to 99 that must appear: backups contain everything and must be kept like passwords; restoring onto a running install needs `REPLACE ALL DATA` typed and signs everyone out; geofences removed; nobody approves or denies their own flight plan; full flight plan editing; digest preferences in the Email Digest card; edit dialogs can clear fields; login lock per username and address.

## Pictures

- About 60 to 80 pictures: one per topic where a picture helps. Topics that are only rules get none.
- Each picture is cropped to the part of the screen the topic talks about (a dialog, a card, a toolbar), not the whole page, with a one-line caption.
- Default theme, computer width. Pictures are files under the frontend's public folder and load only when their topic is shown (lazy loading), so the app does not get slower.
- Pictures are taken by a script (Playwright) so they can all be retaken after a future change in one step. The script and how to run it are documented next to it.
- Data source, in order of preference (builder's call per picture):
  1. The e2e demo data, run locally with the project's own test accounts. Add fake demo records where a screen needs more data.
  2. Staging, after its data is changed to fake names and locations, for screens that need a lot of data (maps with flight tracks, analytics). Pictures are taken in the in-app browser with the owner signed in. Staging can be re-cloned from production afterwards.
- Before a picture is committed, it is checked by eye for real data (names, emails, phones, serials, registrations, addresses, map locations).
- Alt text for every picture describes what it shows.

## Interface details

- The switch is a two-option segmented control using theme tokens, so it works in every theme.
- Computer layout: menu about 240 px wide, sticky while the topic scrolls; topic area fills the rest.
- The current topic is highlighted in the menu; its section is open.
- Keyboard: the switch, menu items and Previous/Next are reachable and usable with the keyboard.

## Testing

- Unit tests (vitest) for: switching views and the choice being remembered; choosing a topic shows only that topic; Previous/Next order; search narrowing the menu and opening the first match; a topic in the address opens that topic; an unknown topic falls back; One page view search still filters as today.
- Update the existing `UserManualPage.test.jsx` placeholder and heading checks to the new text.
- A content check test: every topic has a title and body, ids are unique, and no topic text contains an em dash.
- e2e: one Playwright test that opens the manual, picks a topic in Topics view and switches to One page.

## Left to the builder

- How the content is stored (keep the current `sections` array shape with added topic ids, or move it to its own module).
- Exact topic list and wording, within the shape above.
- Whether the phone topic list is a dropdown panel or a full-height sheet, as long as it closes on selection and on a tap outside.

## Other documents

- `docs/USER_MANUAL.md` becomes a few lines: the manual lives in the app under **User Manual** (sidebar), with the page address `/manual`.
- `README.md` and other docs that link to `docs/USER_MANUAL.md` point to the in-app manual instead.
