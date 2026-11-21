import { test, expect } from '@playwright/test'

test('app loads authenticated and shows the dashboard', async ({ page }) => {
  await page.goto('/')
  // The dashboard has no literal "Dashboard" heading; the hero shows a greeting
  // ("Good morning/afternoon/evening, E2E Admin") and the sidebar nav is present.
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), E2E Admin/ })).toBeVisible({ timeout: 15_000 })
})

test('desktop page header stays in place while a long page scrolls', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.goto('/manual')
  const search = page.getByRole('button', { name: 'Open search' })
  await expect(search).toBeVisible({ timeout: 15_000 })
  // The one-page manual is far taller than the window, so this really scrolls.
  await page.getByRole('button', { name: 'One page', exact: true }).click()
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight)).toBeGreaterThan(2000)
  await page.evaluate(() => window.scrollTo(0, 1500))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(1000)
  await expect(search).toBeInViewport()
  const box = await search.boundingBox()
  expect(box.y).toBeLessThan(64)
})
