import { test, expect } from '@playwright/test'

// Ops journeys: mission log, training log, flight plan, and checklist
// (template + completion). Runs as the default admin storageState. Admin
// qualifies as pilot (Add Mission / Add Training / Submit Plan / Complete
// Checklist) and supervisor (Create Template), so a single role exercises
// every create control. The suite shares one seeded DB, so each entity gets a
// unique, searchable identifier in its title/name and we assert only on OUR
// row, never on global counts.
//
// Real UI used (read from src/pages/{MissionLogPage,TrainingLogPage,
// FlightPlansPage,ChecklistPage}.jsx):
//   - Mission: "Add Mission" -> Modal[role=dialog] "Add Mission"; required
//     input#title + input#date (prefilled today); submit "Add Mission". The
//     "Search missions..." box matches title; the Title cell shows it.
//   - Training: "Add Training" -> Modal "Add Training"; required input#title +
//     input#date + select#training-type (default Recurrent); submit "Add
//     Training". "Search training..." matches title.
//   - Flight plan: "Submit Plan" -> custom modal (NOT role=dialog) heading
//     "Submit Flight Plan"; required input#title, input#planned-date-time,
//     select#pilot; submit "Submit Plan". Row Title cell shows it.
//   - Checklist: "Create Template" (supervisor) -> Modal "Create Checklist
//     Template"; required input#name + >=1 item label; submit "Create
//     Template" -> card on Templates tab. Then "Complete Checklist" -> Modal
//     "Complete Pre-Flight Checklist"; select#template + select#pilot, check
//     the item, submit "Submit Checklist" -> row on Completions tab.

const STAMP = Date.now()

async function goto(page, linkName, urlRe) {
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('link', { name: linkName, exact: true }).click()
  await expect(page).toHaveURL(urlRe)
}

test.describe('ops journeys', () => {
  test('mission log: create a mission and see it in the list', async ({ page }) => {
    const title = `E2E-OPS-Mission-${STAMP}`
    await goto(page, 'Mission Log', /\/missions(?:$|[/?])/)

    await page.getByRole('button', { name: 'Add Mission' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Add Mission' })).toBeVisible()

    await modal.locator('#title').fill(title)
    await modal.locator('#date').fill('2026-06-15')
    await modal.getByRole('button', { name: 'Add Mission' }).click()

    // Primary success signal: the created row appears. Wait for it first so a
    // slightly-slow modal teardown under dev-server load doesn't fail a good create.
    const myRow = page.getByRole('row').filter({ hasText: title })
    await expect(myRow).toBeVisible({ timeout: 15_000 })
    await expect(modal).toBeHidden({ timeout: 15_000 })
    await expect(myRow).toContainText('2026-06-15')
  })

  test('training log: create a training entry and see it in the list', async ({ page }) => {
    const title = `E2E-OPS-Training-${STAMP}`
    await goto(page, 'Training Log', /\/training(?:$|[/?])/)

    await page.getByRole('button', { name: 'Add Training' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Add Training' })).toBeVisible()

    await modal.locator('#title').fill(title)
    await modal.locator('#date').fill('2026-06-15')
    await modal.locator('#training-type').selectOption('Proficiency')
    await modal.getByRole('button', { name: 'Add Training' }).click()

    // Primary success signal: the created row appears. Wait for it first so a
    // slightly-slow modal teardown under dev-server load doesn't fail a good create.
    const myRow = page.getByRole('row').filter({ hasText: title })
    await expect(myRow).toBeVisible({ timeout: 15_000 })
    await expect(modal).toBeHidden({ timeout: 15_000 })
    await expect(myRow).toContainText('Proficiency')
  })

  test('flight plan: submit a plan and see it in the list', async ({ page }) => {
    const title = `E2E-OPS-Plan-${STAMP}`
    // Flight Plans nav label can carry a pending-count badge; match by prefix.
    await page.goto('/')
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
    await page.getByRole('link', { name: /^Flight Plans/ }).click()
    await expect(page).toHaveURL(/\/flight-plans(?:$|[/?])/)

    await page.getByRole('button', { name: 'Submit Plan' }).click()
    // FlightPlansPage uses a custom modal (no role=dialog); match by heading.
    const modal = page.locator('div').filter({ has: page.getByRole('heading', { name: 'Submit Flight Plan' }) }).last()
    await expect(page.getByRole('heading', { name: 'Submit Flight Plan' })).toBeVisible()

    await modal.locator('#title').fill(title)
    await modal.locator('#planned-date-time').fill('2026-06-15T10:00')
    await modal.locator('#pilot').selectOption({ label: 'E2E Seedpilot' })
    await modal.getByRole('button', { name: 'Submit Plan' }).click()

    // Primary success signal: the created row appears. Wait for it first so a
    // slightly-slow modal teardown under dev-server load doesn't fail a good create.
    const myRow = page.getByRole('row').filter({ hasText: title })
    await expect(myRow).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: 'Submit Flight Plan' })).toBeHidden({ timeout: 15_000 })
    await expect(myRow).toContainText('E2E Seedpilot')
    await expect(myRow).toContainText('pending')
  })

  test('checklist: create a template then complete it', async ({ page }) => {
    const name = `E2E-OPS-Checklist-${STAMP}`
    const itemLabel = `Inspect ${name}`
    await goto(page, 'Checklists', /\/checklists(?:$|[/?])/)

    // ── Create a template (supervisor) ──────────────────────────────
    await page.getByRole('button', { name: 'Create Template' }).click()
    const tplModal = page.getByRole('dialog')
    await expect(tplModal.getByRole('heading', { name: 'Create Checklist Template' })).toBeVisible()

    await tplModal.locator('#name').fill(name)
    // The builder seeds one empty required item row; fill its label.
    await tplModal.getByPlaceholder('Item 1...').fill(itemLabel)
    await tplModal.getByRole('button', { name: 'Create Template' }).click()

    // Primary success signal: the created template card appears. Wait for it
    // first so a slightly-slow modal teardown doesn't fail a good create.
    const card = page.locator('h3', { hasText: name })
    await expect(card).toBeVisible({ timeout: 15_000 })
    await expect(tplModal).toBeHidden({ timeout: 15_000 })

    // ── Complete the template ───────────────────────────────────────
    await page.getByRole('button', { name: 'Complete Checklist' }).click()
    const compModal = page.getByRole('dialog')
    await expect(compModal.getByRole('heading', { name: 'Complete Pre-Flight Checklist' })).toBeVisible()

    await compModal.locator('#template').selectOption({ label: name })
    await compModal.locator('#pilot').selectOption({ label: 'E2E Seedpilot' })
    // The single required item must be checked or the completion is "failed".
    // Each item renders a card (the only buttons inside the form, besides the
    // footer, are the per-item toggles); with one item there is exactly one
    // such toggle, sitting next to the label. Find the card by label, click it.
    await expect(compModal.getByText(itemLabel)).toBeVisible()
    const toggle = compModal
      .locator('div.border.rounded-lg')
      .filter({ hasText: itemLabel })
      .getByRole('button')
    await toggle.click()
    await expect(compModal.getByText('Some required items are not checked')).toBeHidden()
    await compModal.getByRole('button', { name: 'Submit Checklist' }).click()

    // On success the page switches to the Completions tab and reloads.
    // Primary success signal: the completion row appears. Wait for it first so a
    // slightly-slow modal teardown doesn't fail a good completion.
    const myRow = page.getByRole('row').filter({ hasText: name })
    await expect(myRow).toBeVisible({ timeout: 15_000 })
    await expect(compModal).toBeHidden({ timeout: 15_000 })
    await expect(myRow).toContainText('E2E Seedpilot')
  })
})
