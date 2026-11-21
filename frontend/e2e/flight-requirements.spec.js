import { test, expect } from '@playwright/test'

// Flight requirement journey: an admin opens the Flight Requirements tab of
// the Compliance page from the sidebar, creates a monthly requirement for all active
// pilots, sees it in the list and on the dashboard "This Period" tile, switches
// it off and on again from the list, then deletes it. Runs as the default admin
// storageState. A new requirement has no saved results, so it can be deleted;
// the name is unique per run so reruns never collide.

async function openRequirements(page) {
  await page.goto('/')
  await page.getByRole('navigation').getByRole('link', { name: 'Compliance', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Compliance', exact: true })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('tab', { name: 'Flight Requirements', exact: true }).click()
  await expect(page).toHaveURL(/\/compliance\?tab=requirements$/)
}

test('admin creates a monthly flight requirement and sees it on the dashboard', async ({ page }) => {
  const name = `E2E monthly hour ${Date.now()}`

  await openRequirements(page)
  await page.getByRole('button', { name: 'New requirement', exact: true }).click()

  const form = page.getByRole('form', { name: 'New requirement' })
  await form.getByLabel('Name', { exact: true }).fill(name)
  await expect(form.getByRole('switch', { name: 'Requirement is active' })).toHaveAttribute('aria-checked', 'true')
  await expect(form.getByLabel('Period', { exact: true })).toHaveValue('calendar_month')
  await expect(form.getByRole('radio', { name: 'All active pilots' })).toBeChecked()
  await form.getByLabel('Hours', { exact: true }).fill('1')
  await expect(form.getByText(/all active pilots/i).last()).toBeVisible()
  await form.getByRole('button', { name: 'Save requirement' }).click()
  await expect(form).toBeHidden()

  const row = page.getByRole('listitem').filter({ has: page.getByText(name, { exact: true }) })
  try {
    await expect(row).toBeVisible({ timeout: 15_000 })
    await expect(row).toContainText('Active')
    await expect(row).toContainText(/days? left/)

    await page.goto('/')
    const tile = page.getByRole('region', { name: 'This Period' })
    await expect(tile.getByRole('listitem', { name })).toBeVisible({ timeout: 15_000 })

    await openRequirements(page)
    await row.getByRole('button', { name: `Switch off ${name}`, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Switch off', exact: true }).click()
    await expect(row).toContainText('Inactive', { timeout: 15_000 })
    await row.getByRole('button', { name: `Switch on ${name}`, exact: true }).click()
    await expect(row.getByRole('button', { name: `Switch off ${name}`, exact: true })).toBeVisible({ timeout: 15_000 })
  } finally {
    // The old address still lands on the tab.
    await page.goto('/requirements')
    await expect(page).toHaveURL(/\/compliance\?tab=requirements$/)
    await page.getByRole('button', { name: `Delete ${name}`, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page.getByText(name, { exact: true })).toHaveCount(0)
  }
})
