import { test, expect } from '@playwright/test'

// Currency rule journey: an admin opens Settings, creates a rule on one fleet
// model from the model picker, and the rule list shows that model. Runs as the
// default admin storageState. The seeded fleet holds a Skydio X10 and a DJI
// Matrice 30, so the picker offers both as toggle chips.

test('admin creates a currency rule on one fleet model from the picker', async ({ page }) => {
  const name = `E2E model rule ${Date.now()}`

  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Currency Rules' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: 'New Rule', exact: true }).click()

  const modal = page.getByRole('dialog')
  await modal.locator('#rule-name').fill(name)

  // New rules start on All aircraft.
  const all = modal.getByRole('button', { name: 'All aircraft', exact: true })
  await expect(all).toHaveAttribute('aria-pressed', 'true')

  // One chip per fleet model, labelled with its active aircraft count.
  const x10 = modal.getByRole('button', { name: /^X10 \(\d+\)$/ })
  await expect(x10).toBeVisible({ timeout: 15_000 })
  await x10.click()
  await expect(x10).toHaveAttribute('aria-pressed', 'true')
  await expect(all).toHaveAttribute('aria-pressed', 'false')

  await modal.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(modal).toBeHidden()

  await expect(page.getByText(name)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('X10 only').first()).toBeVisible()
})
