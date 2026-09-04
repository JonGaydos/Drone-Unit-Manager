import { test, expect } from '@playwright/test'
import { getAdminToken, createFlight } from './helpers/seed.js'

// Flights journey: log a flight via the UI, find it, filter to it, bulk-update
// it, and export CSV. Runs as the default admin storageState. Admin qualifies as
// pilot (so "Add Flight" + the modal show), supervisor (bulk selection + the
// reassign/purpose/reviewed/delete toolbar), and admin (detail-page Edit), so a
// single role exercises every control. The suite shares one seeded DB, so we tag
// our flight with a unique, searchable takeoff address and assert only on OUR row.
//
// Real UI used (read from src/pages/FlightsPage.jsx + FlightDetailPage.jsx):
//   - Create: "Add Flight" button -> Modal "Add Flight" with select#pilot,
//     select#vehicle, input#date, input#case-number, input#takeoff-address;
//     submit button "Add Flight". The list "Search flights..." box matches
//     pilot/vehicle/purpose/takeoff_address (NOT case_number), so the unique tag
//     lives in takeoff_address (also shown in the Location column + detail page).
//   - Filter: Pilot dropdown (select#pilot-1, server-side) + the search box.
//   - Bulk: per-row checkbox aria-label="Select flight <id>", then the
//     supervisor toolbar "Mark reviewed" button (POST /flights/bulk-update).
//   - Export: "Export CSV" button -> api.download('/export/flights/csv'), which
//     clicks a synthetic <a download>, firing a real Playwright download event.

const TAG = `E2E-FLT-${Date.now()}`

async function gotoFlights(page) {
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  // The Flights nav link's accessible name can carry a review badge ("Flights N"),
  // so match by route prefix rather than exact text.
  await page.getByRole('link', { name: /^Flights/ }).click()
  await expect(page).toHaveURL(/\/flights(?:$|[/?])/)
}

test.describe('flights journey', () => {
  test('log a flight, find it on its detail page', async ({ page }) => {
    await gotoFlights(page)

    await page.getByRole('button', { name: 'Add Flight' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Add Flight' })).toBeVisible()

    // Choose a seeded pilot + seeded vehicle by their visible option labels.
    await modal.locator('#pilot').selectOption({ label: 'E2E Seedpilot' })
    await modal.locator('#vehicle').selectOption({ label: 'E2E Seed Drone' })
    await modal.locator('#date').fill('2026-06-15')
    await modal.locator('#case-number').fill(TAG)
    // Unique, searchable identifier (search matches takeoff_address).
    await modal.locator('#takeoff-address').fill(`${TAG} Launch Site`)
    await modal.getByRole('button', { name: 'Add Flight' }).click()

    // Modal closes and the new row appears (its Location cell shows our tag).
    await expect(modal).toBeHidden({ timeout: 10_000 })
    const myRow = page.getByRole('row').filter({ hasText: `${TAG} Launch Site` })
    await expect(myRow).toBeVisible({ timeout: 10_000 })
    await expect(myRow).toContainText('E2E Seedpilot')

    // Open its detail page; assert a field we entered renders (case # + address).
    await myRow.getByRole('link', { name: /^#\d+$/ }).click()
    await expect(page).toHaveURL(/\/flights\/\d+/)
    await expect(page.getByText(TAG, { exact: true })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(`${TAG} Launch Site`)).toBeVisible()
  })

  // This test creates its OWN flight over the API (independent of test 1) so it
  // can run in isolation; it then drives filter/bulk/export through the real UI.
  test('filter narrows the list to the flight, bulk-mark-reviewed, then export CSV', async ({ page, request }) => {
    const tag2 = `E2E-FLT-${Date.now()}-bulk`
    const token = getAdminToken()
    await createFlight(request, token, { takeoff_address: `${tag2} Launch Site`, review_status: 'needs_review' })

    await gotoFlights(page)

    // Search by the unique takeoff address; only our row should remain.
    const searchBox = page.getByPlaceholder('Search flights...')
    await searchBox.fill(`${tag2} Launch Site`)
    const myRow = page.getByRole('row').filter({ hasText: `${tag2} Launch Site` })
    await expect(myRow).toBeVisible({ timeout: 10_000 })
    // A non-matching seeded flight (Training purpose) is hidden by the search.
    await expect(page.getByRole('row').filter({ hasText: 'Training' })).toHaveCount(0)

    // The flight starts as "Needs Review". Select its row checkbox (supervisor
    // bulk action) and mark it reviewed; assert OUR row flips to "Reviewed".
    await expect(myRow).toContainText('Needs Review')
    await myRow.getByRole('checkbox').check()
    await expect(page.getByText('1 selected')).toBeVisible()
    await page.getByRole('button', { name: 'Mark reviewed' }).click()

    // After the bulk update, load() reloads the table and clears the selection
    // (the search text persists), so the same single row remains visible.
    await expect(page.getByText('1 selected')).toBeHidden({ timeout: 10_000 })
    const reviewedRow = page.getByRole('row').filter({ hasText: `${tag2} Launch Site` })
    await expect(reviewedRow).toBeVisible({ timeout: 10_000 })
    await expect(reviewedRow).toContainText('Reviewed')
    await expect(reviewedRow).not.toContainText('Needs Review')

    // CSV export: clicking "Export CSV" fires a real browser download.
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export CSV' }).click(),
    ])
    const name = download.suggestedFilename()
    expect(name).toBeTruthy()
    expect(name).toMatch(/\.csv$/)
  })
})
