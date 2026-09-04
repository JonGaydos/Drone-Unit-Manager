import { test, expect } from '@playwright/test'

test('app loads authenticated and shows the dashboard', async ({ page }) => {
  await page.goto('/')
  // The dashboard has no literal "Dashboard" heading; the hero shows a greeting
  // ("Good morning/afternoon/evening, E2E Admin") and the sidebar nav is present.
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), E2E Admin/ })).toBeVisible({ timeout: 15_000 })
})
