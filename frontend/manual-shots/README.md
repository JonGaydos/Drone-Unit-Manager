# Manual pictures

Takes the pictures used by the in-app User Manual.

## Run

    npm run manual:shots

The run starts the local e2e backend on a fresh, empty database, creates the
e2e admin, fills the database with fake demo data (`seed-demo.js`), then saves
one PNG per entry in `shots.js` to `public/manual-pictures/`.

## Rules

- Fake data only: made-up names, `@example.com` emails, `555-01xx` phones,
  `DEMO-` serials, `FA-DEMO-` registrations, text locations and no coordinates.
- Never point this at staging or production.
- Open every new picture and check it by eye before you commit it.
- Add a picture by adding an entry to `SHOTS` in `shots.js`, then set the
  topic's `image` in `src/pages/manual/content.json`.
- This folder is not part of the normal `npx playwright test` run.
