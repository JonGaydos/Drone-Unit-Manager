/* global process */
import { test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { getAdminToken } from '../e2e/helpers/seed.js'
import { seedDemo } from './seed-demo.js'
import { SHOTS } from './shots.js'

const OUT_DIR = path.resolve(process.cwd(), 'public/manual-pictures')

test.describe.configure({ mode: 'serial' })

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext()
  try {
    await seedDemo(request, getAdminToken())
  } finally {
    await request.dispose()
  }
})

mkdirSync(OUT_DIR, { recursive: true })

for (const shot of SHOTS) {
  test(shot.file, async ({ page }) => {
    await page.goto(shot.route)
    await page.waitForLoadState('networkidle')
    if (shot.prepare) await shot.prepare(page)
    await page.waitForLoadState('networkidle')
    await shot.target(page).screenshot({ path: path.join(OUT_DIR, shot.file) })
  })
}
