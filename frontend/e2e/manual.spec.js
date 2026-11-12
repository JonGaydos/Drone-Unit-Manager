import { test, expect } from '@playwright/test'
import { sections } from '../src/pages/manual/content.js'

// Titles come from the real content so a later rewrite does not break this test.
test('manual: pick a topic, switch to One page, and keep the choice after reload', async ({ page }) => {
  await page.goto('/manual')
  await expect(page.getByRole('main').getByRole('heading', { name: 'User Manual', level: 1 })).toBeVisible({ timeout: 15_000 })

  const menu = page.getByRole('navigation', { name: 'Manual topics' })
  const topic = sections[0].topics[1] || sections[0].topics[0]
  await menu.getByRole('button', { name: topic.title, exact: true }).click()
  await expect(page.getByRole('heading', { name: topic.title, level: 2, exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'One page' }).click()
  for (const section of sections.slice(0, 3)) {
    await expect(page.getByRole('heading', { name: section.title, level: 2, exact: true })).toBeVisible()
  }

  await page.reload()
  await expect(page.getByRole('button', { name: 'One page' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('heading', { name: sections[1].title, level: 2, exact: true })).toBeVisible()
})
