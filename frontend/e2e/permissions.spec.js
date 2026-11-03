import { test, expect } from '@playwright/test'
import { api, getAdminToken, getPilotToken, createFlight } from './helpers/seed.js'

// Role permissions journey: the admin grants the pilot role "Delete flights" at
// Own in Settings > Users > Role Permissions. The pilot login then deletes a
// flight it logged, and is refused on a flight the admin logged. The pilot role
// default for flight delete is None, so the grid change is what makes the
// difference. The pilot's requests go over the API with its saved login, so the
// shared login rate limit is not spent. The grid is reset afterwards so later
// specs see the defaults.

const PILOT_DELETE_CELL = 'Pilot, Flights, Delete'

test.describe('role permissions journey', () => {
  test('admin grants pilots flight delete at Own, pilot deletes only their own flight', async ({ page, request }) => {
    const adminToken = getAdminToken()
    const pilot = api(request, getPilotToken())

    try {
      await page.goto('/settings')
      await page.getByRole('button', { name: 'Users', exact: true }).click()
      const cell = page.getByLabel(PILOT_DELETE_CELL, { exact: true })
      await expect(cell).toHaveValue('none', { timeout: 15_000 })

      await cell.selectOption({ label: 'Own' })
      await page.getByRole('button', { name: 'Save changes' }).click()
      await expect(page.getByText('Permissions saved')).toBeVisible({ timeout: 10_000 })
      await expect(cell).toHaveValue('own')

      const ownFlight = await (await pilot.post('/flights', { notes: 'E2E pilot own flight' })).json()
      const otherFlight = await createFlight(request, adminToken, { notes: 'E2E admin logged flight' })

      expect((await pilot.del(`/flights/${otherFlight.id}`)).status()).toBe(403)
      expect((await pilot.del(`/flights/${ownFlight.id}`)).status()).toBe(200)

      const remaining = await api(request, adminToken).get(`/flights/${otherFlight.id}`)
      expect(remaining.ok()).toBe(true)
    } finally {
      await api(request, adminToken).post('/permissions/reset', {})
    }
  })
})
