import { test, expect } from '@playwright/test'

// Signals that the app is authenticated and showing the dashboard: the sidebar
// Dashboard link is present and the hero greeting h2 is visible. There is no
// literal "Dashboard" heading. The greeting lives in DashboardPage, which is
// gated behind a dozen parallel data fetches, so it can take several seconds to
// paint; use a generous timeout (matching the harness elsewhere).
async function expectAuthenticated(page) {
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening),/ })).toBeVisible({ timeout: 15_000 })
}

test.describe('auth + role gating', () => {
  test.describe('anonymous', () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test('login as admin lands authenticated', async ({ page }) => {
      await page.goto('/login')
      await page.getByLabel('Username').fill('e2eadmin')
      await page.getByLabel('Password', { exact: true }).fill('E2eAdminPass1')
      await page.getByRole('button', { name: 'Sign In' }).click()
      await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 })
      await expectAuthenticated(page)
    })

    test('bad credentials show an inline error and stay on /login', async ({ page }) => {
      await page.goto('/login')
      await page.getByLabel('Username').fill('e2eadmin')
      await page.getByLabel('Password', { exact: true }).fill('definitely-wrong-password')
      await page.getByRole('button', { name: 'Sign In' }).click()

      // A bad login is a credentials error, not a session expiry: the client
      // exempts /auth/login from the global 401 handler, so LoginPage shows the
      // real backend detail inline instead of clearing storage and redirecting.
      await expect(page.getByText(/invalid credentials/i)).toBeVisible({ timeout: 15_000 })
      await expect(page).toHaveURL(/\/login/, { timeout: 15_000 })
      await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible()
      const token = await page.evaluate(() => localStorage.getItem('token'))
      expect(token).toBeNull()
    })
  })

  test('logout clears the session and returns to login', async ({ page }) => {
    // Default admin storageState.
    await page.goto('/')
    await expectAuthenticated(page)

    // Real control: the sidebar user section has a button aria-label="Log out".
    await page.getByRole('button', { name: 'Log out' }).click()

    // Route guard redirects unauthenticated users to /login.
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 })
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible()

    // Token is gone from localStorage.
    const token = await page.evaluate(() => localStorage.getItem('token'))
    expect(token).toBeNull()
  })

  test('admin sees the Audit Log nav item', async ({ page }) => {
    // Default admin storageState.
    await page.goto('/')
    await expectAuthenticated(page)
    await expect(page.getByRole('link', { name: 'Audit Log', exact: true })).toBeVisible()
  })

  test.describe('as pilot', () => {
    test.use({ storageState: 'e2e/.auth/pilot.json' })

    test('pilot does not see the admin-only Audit Log nav item', async ({ page }) => {
      await page.goto('/')
      // Pilot is genuinely logged in: normal nav links are visible. (Pilots has
      // no badge, unlike Flights whose accessible name becomes "Flights N" when
      // the review badge is present.)
      await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
      await expect(page.getByRole('link', { name: 'Pilots', exact: true })).toBeVisible()
      // Audit Log is admin-only and must be absent.
      await expect(page.getByRole('link', { name: 'Audit Log', exact: true })).toHaveCount(0)
    })
  })
})
