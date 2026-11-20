import { test, expect } from '@playwright/test'

// Flight requirement journey: an admin opens Settings, Flight Requirements,
// creates a monthly requirement for all active pilots, sees it in the list and
// on the dashboard "This Period" tile, then deletes it. Runs as the default
// admin storageState. A new requirement has no saved results, so it can be
// deleted; the name is unique per run so reruns never collide.

test('admin creates a monthly flight requirement and sees it on the dashboard', async ({ page }) => {
  const name = `E2E monthly hour ${Date.now()}`

  await page.goto('/settings')
  await page.getByRole('button', { name: 'Flight Requirements', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Flight Requirements', exact: true })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'New requirement', exact: true }).click()

  const form = page.getByRole('form', { name: 'New requirement' })
  await form.getByLabel('Name', { exact: true }).fill(name)
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

    await page.goto('/')
    const tile = page.getByRole('region', { name: 'This Period' })
    await expect(tile.getByRole('listitem', { name })).toBeVisible({ timeout: 15_000 })
  } finally {
    await page.goto('/settings')
    await page.getByRole('button', { name: 'Flight Requirements', exact: true }).click()
    await page.getByRole('button', { name: `Delete ${name}`, exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page.getByText(name, { exact: true })).toHaveCount(0)
  }
})
