import { test, expect } from '@playwright/test'

// Dashboard journey: navigate to the app root (default admin storageState) and
// assert the bento dashboard renders end-to-end against the seeded baseline
// (2 vehicles, 2 pilot records, 1 Training flight, 1 cert type, 1 expired cert).
//
// This is the React #31-class guard end-to-end: the production crash was an
// object rendered raw into JSX, which paints the literal "[object Object]".
// We assert that string is absent anywhere on the page on a normal load.
//
// Real UI used (read from src/pages/DashboardPage.jsx):
//   - Hero h2 greeting /Good (morning|afternoon|evening),/ (always renders).
//   - Four StatTiles: "Flights (30d)", "Hours (30d)", "Active Pilots",
//     "Fleet Size" — labels always render; values come from /dashboard/stats
//     and /dashboard/trends (fleet_size reflects the 2 seeded vehicles).
//   - Section headings: "Recent Flights", "Currency Risk", "Activity by Month",
//     "Top Pilots (30d)", "Top Vehicles (30d)", "Locations" — always render.
//   - Recent Flights lists the 1 seeded Training flight (pilot "E2E Seedpilot").
//   - WeatherTile: depends on /weather/briefing using the org location. With no
//     mocked external call it may render the "Weather widget unavailable"
//     placeholder instead of the "Weather" heading; both are non-crash states,
//     so we accept either.
//   - No error banner on a normal seeded load.
//
// The dashboard fires ~12 parallel fetches and can take >5s; first-content
// assertions use 15s timeouts. Web-first assertions only, no hardcoded sleeps.

test.describe('dashboard journey', () => {
  test('dashboard loads with seeded data', async ({ page }) => {
    await page.goto('/')

    // Authed signal + hero greeting (gated behind the parallel fetch batch).
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true }))
      .toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening),/ }))
      .toBeVisible({ timeout: 15_000 })

    // Stat tile labels always render once loading resolves.
    await expect(page.getByText('Flights (30d)')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Hours (30d)')).toBeVisible()
    await expect(page.getByText('Active Pilots')).toBeVisible()
    await expect(page.getByText('Fleet Size')).toBeVisible()

    // Fleet Size tile reflects the 2 seeded vehicles (a real value, not 0).
    const fleetTile = page.getByText('Fleet Size').locator('xpath=ancestor::div[1]')
    await expect(fleetTile.getByText('2', { exact: true })).toBeVisible()

    // Section tiles render their headings (real content, not error/empty crash).
    await expect(page.getByRole('heading', { name: /Recent Flights/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Currency Risk/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Activity by Month/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Top Pilots/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Locations/ })).toBeVisible()

    // The single seeded Training flight renders in the Recent Flights list,
    // proving the page mounted with real data rather than an empty state.
    await expect(page.getByText('E2E Seedpilot').first()).toBeVisible()

    // Weather tile: it either renders the "Weather" heading (live briefing) or
    // the "Weather widget unavailable" placeholder (no external data). Either is
    // a non-crash render; require one of them to be present.
    const weatherHeading = page.getByRole('heading', { name: /Weather/ })
    const weatherPlaceholder = page.getByText('Weather widget unavailable')
    await expect(weatherHeading.or(weatherPlaceholder).first()).toBeVisible()

    // No error banner / alert on a normal seeded load.
    await expect(page.getByRole('alert')).toHaveCount(0)

    // React #31 regression guard end-to-end: an object stringified into JSX must
    // never appear on the page.
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })
})
