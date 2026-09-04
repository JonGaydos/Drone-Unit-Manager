import { test, expect } from '@playwright/test'

// Settings save + feature-area happy-path walks. Runs as the default admin
// storageState. One real mutation (Settings org name) plus read-only renders of
// every remaining feature page, each asserting a real page-specific element, no
// error banner, and no "[object Object]" (the React #31 stringified-object guard).
//
// Real UI used (read from src/pages/*):
//   - Settings: General tab, Organization Name input #setting-org_name (non-secret).
//     "Save Settings" -> handleSave -> PUT /settings/bulk. Persistence verified by
//     reloading and re-reading the input value.
//   - Integrations: reached via the Settings page "Integrations" tab (there is no
//     standalone /integrations route or sidebar link). Renders the lazy
//     IntegrationsPage: h1 "Integrations", "Drone Providers" section, Skydio card.
//   - Calendar: h1 "Calendar", FullCalendar (.fc) renders a month title + day grid.
//   - Documents: folder sidebar h2 "Folders" + "Document Storage" empty-state (no
//     folder selected on load).
//   - Media: h1 "Photo Gallery"; with no photos seeded it shows the "No Photos Yet"
//     empty state.
//   - Reports: h2 "Report Builder" + "Report Preview". Generate (default Flight
//     Summary) -> POST /reports/generate -> preview renders a result section.
//   - Analytics: ChartCard titles render from the seeded flight ("Pilot Hours
//     Leaderboard", "All Time Flights by Purpose") + a recharts SVG.
//   - Airspace: Leaflet map (.leaflet-container) + the radius control. External
//     ADS-B is only hit on map click, so plain load is deterministic.
//   - Weather: h1 "Pre-Flight Weather Briefing" + Location panel. The org-location
//     briefing fetch hits an external API, so we assert only the always-present
//     shell, not the briefing body.

async function goto(page, linkName, urlRe) {
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('link', { name: linkName, exact: true }).click()
  await expect(page).toHaveURL(urlRe)
}

test.describe('settings + feature-area walks', () => {
  test('settings: change org name, save, and confirm it persists after reload', async ({ page }) => {
    const orgName = `E2E Org ${Date.now()}`
    await goto(page, 'Settings', /\/settings(?:$|[/?])/)

    // General tab is the default. Organization Name is a non-secret display field.
    const orgInput = page.locator('#setting-org_name')
    await expect(orgInput).toBeVisible({ timeout: 15_000 })
    await orgInput.fill(orgName)

    await page.getByRole('button', { name: 'Save Settings' }).click()
    // Primary success signal: the save toast. Assert it before reloading so a
    // slow PUT doesn't race the reload.
    await expect(page.getByText('Settings saved!')).toBeVisible({ timeout: 15_000 })

    // Reload and confirm the persisted value is reflected in the input.
    await page.reload()
    const reloaded = page.locator('#setting-org_name')
    await expect(reloaded).toBeVisible({ timeout: 15_000 })
    await expect(reloaded).toHaveValue(orgName, { timeout: 15_000 })
  })

  test('integrations: provider and sync section renders', async ({ page }) => {
    // Integrations has no sidebar link; it lives behind the Settings page tab.
    await goto(page, 'Settings', /\/settings(?:$|[/?])/)
    await page.getByRole('button', { name: 'Integrations', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Integrations', exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Drone Providers' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Skydio', exact: true })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('calendar: FullCalendar grid renders', async ({ page }) => {
    await goto(page, 'Calendar', /\/calendar(?:$|[/?])/)
    await expect(page.getByRole('heading', { name: 'Calendar', exact: true })).toBeVisible({ timeout: 15_000 })
    // FullCalendar mounts its own DOM; assert the calendar root, its title
    // (current month/year) and at least one day cell rendered.
    await expect(page.locator('.fc')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('.fc-toolbar-title')).not.toBeEmpty({ timeout: 15_000 })
    await expect(page.locator('.fc-daygrid-day').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('documents: folder tree and documents area render', async ({ page }) => {
    await goto(page, 'Documents', /\/documents(?:$|[/?])/)
    await expect(page.getByRole('heading', { name: 'Folders' })).toBeVisible({ timeout: 15_000 })
    // No folder selected on load -> the main pane shows the Document Storage prompt.
    await expect(page.getByRole('heading', { name: 'Document Storage' })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('media: photo gallery renders', async ({ page }) => {
    await goto(page, 'Photo Gallery', /\/media(?:$|[/?])/)
    await expect(page.getByRole('heading', { name: 'Photo Gallery', exact: true })).toBeVisible({ timeout: 15_000 })
    // No photos seeded -> the gallery shows its empty state.
    await expect(page.getByRole('heading', { name: 'No Photos Yet' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('reports: builder renders and a report generates', async ({ page }) => {
    await goto(page, 'Reports', /\/reports(?:$|[/?])/)
    await expect(page.getByRole('heading', { name: 'Report Builder' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Report Preview' })).toBeVisible()

    // Default report type is Flight Summary; generate it (previews in-page).
    await page.locator('#report-type').selectOption('flight_summary')
    await page.getByRole('button', { name: 'Generate', exact: true }).click()

    // Success signal: the preview shows a result. The seeded DB has one flight, so
    // either a summary/table or the explicit "no data" line renders — both prove a
    // successful generate (no error banner). Assert the result section, not the
    // empty "Configure your report settings" placeholder.
    const result = page
      .getByRole('heading', { name: 'Flight Summary' })
      .or(page.getByText('No data matches the selected filters'))
    await expect(result).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('Configure your report settings and click Generate to see a preview.')).toHaveCount(0)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('analytics: charts and leaderboard render', async ({ page }) => {
    await goto(page, 'Analytics', /\/analytics(?:$|[/?])/)
    // Section titles come from real ChartCards; the leaderboard reads the seeded
    // pilot-hours data.
    await expect(page.getByRole('heading', { name: 'Pilot Hours Leaderboard' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'All Time Flights by Purpose' })).toBeVisible()
    // Recharts renders an SVG chart container in the real browser.
    await expect(page.locator('.recharts-surface').first()).toBeVisible({ timeout: 15_000 })
    // The seeded flight's pilot appears in the leaderboard table.
    await expect(page.getByText('E2E Seedpilot').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('airspace: leaflet map and controls render', async ({ page }) => {
    await goto(page, 'Airspace', /\/airspace(?:$|[/?])/)
    // Leaflet mounts a real map in Chromium.
    await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 15_000 })
    // Page-specific control + the click-to-search prompt (no point selected yet).
    await expect(page.locator('#radius')).toBeVisible()
    await expect(page.getByText('Click anywhere on the map to set your location')).toBeVisible({ timeout: 15_000 })
    // External ADS-B is only hit on a map click, so a plain load shows no error.
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('weather: briefing page renders', async ({ page }) => {
    await goto(page, 'Weather', /\/weather(?:$|[/?])/)
    await expect(page.getByRole('heading', { name: 'Pre-Flight Weather Briefing' })).toBeVisible({ timeout: 15_000 })
    // The Location panel is always present (the org-location briefing fetch hits an
    // external API, so we assert the deterministic shell, not the briefing body).
    await expect(page.getByRole('heading', { name: 'Location', exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('#latitude')).toBeVisible()
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })
})
