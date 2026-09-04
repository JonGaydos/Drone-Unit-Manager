import { test, expect } from '@playwright/test'
import { gotoSection } from './helpers/app.js'

// Pilots + compliance journey: add a pilot through the real UI and find OUR row,
// open its detail page, confirm the Certifications matrix renders end-to-end with
// the seeded cert type + pilots, then confirm the Compliance dashboard renders the
// seeded expired-certification as a red (critical) attention item. Runs as the
// default admin storageState; admin qualifies as supervisor, so the "Add Pilot" /
// "Assign Cert" controls render.
//
// The suite shares one seeded DB across re-runs, so the new pilot is created with a
// unique, searchable last name and we assert only on OUR row (never global counts).
//
// Real UI used (read from src/pages/PilotsPage.jsx, CertificationsPage.jsx,
// CompliancePage.jsx + their Vitest tests):
//   - Pilots: "Add Pilot" button opens a role="dialog" Modal headed "Add Pilot".
//     Fields: #pilot-first_name, #pilot-last_name, #pilot-email (+ phones / badge /
//     status / notes). Submit button text equals "Add Pilot". List rows: the name
//     cell links to /pilots/:id with text = full_name ("<first> <last>"). The search
//     box matches "<first> <last> <email> <badge>", so a unique last name filters
//     the list to exactly our row.
//   - Pilot detail: header is a heading with the pilot full_name; the email renders.
//   - Certifications: the "Certification Matrix" tab is default. Each pilot is a row
//     (name links to /pilots/:id); each active cert type is a column header. The
//     seeded cert type is "E2E Part 107"; seeded pilots include "E2E Seedpilot".
//   - Compliance: heading "Compliance Dashboard". The seeded EXPIRED certification
//     (exp 2022-01-01) makes /dashboard/compliance report expired_certifications > 0,
//     which renders a critical (red) "Expired Certifications" row in "Items Requiring
//     Attention" and a non-zero red "Expired Certs" stat card.

async function gotoPilots(page) {
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await gotoSection(page, 'Pilots')
}

test.describe('pilots + compliance journey', () => {
  test('add a pilot via the UI, find it in the list, open its detail page', async ({ page }) => {
    const stamp = Date.now()
    const firstName = 'E2E'
    const lastName = `E2EPILOT${stamp}`
    const fullName = `${firstName} ${lastName}`
    const email = `e2epilot${stamp}@example.com`

    await gotoPilots(page)
    // Wait for a known seeded row before interacting (the list mounts from /pilots).
    // The name cell's link accessible name is "<initials> <full_name>" (avatar
    // initials are inside the anchor), so match on the row text.
    await expect(page.getByRole('row').filter({ hasText: 'E2E Seedpilot' }).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: 'Add Pilot' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Add Pilot' })).toBeVisible()
    await modal.locator('#pilot-first_name').fill(firstName)
    await modal.locator('#pilot-last_name').fill(lastName)
    await modal.locator('#pilot-email').fill(email)
    await modal.getByRole('button', { name: 'Add Pilot' }).click()

    // Modal closes and our row appears. Search by the unique last name to filter
    // the list down to exactly our pilot, then assert on that row.
    await expect(modal).toBeHidden({ timeout: 10_000 })
    await page.getByPlaceholder('Search pilots...').fill(lastName)
    const myRow = page.getByRole('row').filter({ hasText: lastName })
    await expect(myRow).toBeVisible({ timeout: 10_000 })
    await expect(myRow).toContainText(email)

    // Open its detail page; the row has a single name link whose accessible name
    // is "<initials> <full_name>", so match it by the unique full name substring.
    await expect(myRow.getByRole('link')).toContainText(fullName)
    await myRow.getByRole('link').click()
    await expect(page).toHaveURL(/\/pilots\/\d+/)
    await expect(page.getByRole('heading', { name: fullName })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(email).first()).toBeVisible()
  })

  test('certifications matrix renders end to end with the seeded cert type and pilots', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
    await gotoSection(page, 'Certifications')

    // The matrix tab is the default. The seeded cert type is a column header and a
    // seeded pilot is a row link, proving real content (not a crash/empty state).
    await expect(page.getByRole('link', { name: 'E2E Seedpilot', exact: true })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('E2E Part 107', { exact: true })).toBeVisible()
    await expect(page.getByText('No pilots or certifications configured yet')).toHaveCount(0)
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })

  test('compliance dashboard renders the seeded expired certification as a red attention item', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
    await gotoSection(page, 'Compliance')

    await expect(page.getByRole('heading', { name: 'Compliance Dashboard' })).toBeVisible({ timeout: 15_000 })

    // The seeded expired cert drives the red "Expired Certs" stat card and a
    // critical "Expired Certifications" row in "Items Requiring Attention".
    await expect(page.getByText('Items Requiring Attention')).toBeVisible({ timeout: 15_000 })
    const attentionRow = page.getByRole('button').filter({ hasText: 'Expired Certifications' })
    await expect(attentionRow).toBeVisible({ timeout: 15_000 })
    await expect(attentionRow).toContainText('critical')

    // No raw objects leaked anywhere on the dashboard.
    await expect(page.getByText('[object Object]')).toHaveCount(0)
  })
})
