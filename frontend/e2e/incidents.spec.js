import { test, expect } from '@playwright/test'
import { createVehicle } from './helpers/seed.js'
import { gotoSection } from './helpers/app.js'

// Cross-cutting journey: reporting an incident with the grounding flag set, for
// a vehicle that is currently ACTIVE, transitions that vehicle's status to
// `maintenance`. The grounding side effect lives server-side in
// app/routers/incidents.py (_ground_vehicle_if_needed) and only fires when the
// vehicle is active at create time. This spec drives that whole chain through
// the real UI/stack and asserts the vehicle status flip end to end.
//
// Real UI used (read from src/pages/IncidentPage.jsx + VehicleDetailPage.jsx):
//   - Incidents page route is /incidents, sidebar label "Activity Reports".
//   - Create trigger: button "New Report" (visible because admin satisfies
//     isPilot). It opens a role="dialog" Modal headed "Report Incident".
//   - Form fields: #date (defaulted to today), #title (required), #severity,
//     #category, #description (required), #vehicle (vehicle select; option
//     value = vehicle id, label = vehicleDisplayName), and the grounding
//     control: checkbox #equip_grounded labelled "Equipment Grounded".
//   - Submit button text = "Report Incident". On success a toast "Incident
//     reported" shows and the new row appears in the incidents table.
//   - Vehicle detail (/fleet/vehicles/:id) header shows "S/N: <serial>" and a
//     status badge whose text is the raw status (e.g. "maintenance").
//
// Isolation: this flow mutates vehicle status, so it creates its OWN uniquely
// named ACTIVE vehicle (never the shared seed vehicles). The vehicle is created
// via the API seed helper (allowed for the prerequisite only); the grounding
// action itself goes entirely through the UI.
//
// Login budget: the backend rate-limits logins to 5 per 60s per IP and the
// serial suite already sits near that ceiling (only global-setup + auth.spec
// spend real logins). So this spec does NOT call apiLogin; it reuses the admin
// JWT already present in the admin storageState (localStorage `token`) for the
// one prerequisite API call. No extra login is spent. (getAdminToken() in
// helpers/seed.js reads that same token from the storageState file for specs
// that don't already have a page open.)

test.describe('incident grounding journey', () => {
  test('reporting a grounding incident flips an active vehicle to maintenance', async ({ page, request }) => {
    const stamp = Date.now()
    const serial = `E2E-GND-${stamp}`

    // --- Step 1: prerequisite ACTIVE vehicle (API seed helper only) ---
    // Reuse the admin JWT from the loaded admin storageState instead of logging
    // in again (see "Login budget" note above).
    await page.goto('/')
    const token = await page.evaluate(() => localStorage.getItem('token'))
    expect(token).toBeTruthy()
    const vehicle = await createVehicle(request, token, {
      serial_number: serial,
      manufacturer: 'E2E',
      model: 'Grounder',
      status: 'active',
    })
    expect(vehicle.id).toBeTruthy()
    expect(vehicle.status).toBe('active')

    // --- Step 2: report a grounding incident via the UI ---
    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
    await gotoSection(page, 'Activity Reports')

    await page.getByRole('button', { name: 'New Report' }).click()

    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Report Incident' })).toBeVisible({ timeout: 10_000 })

    const title = `E2E Grounding ${stamp}`
    await modal.locator('#title').fill(title)
    await modal.locator('#description').fill('E2E cross-cutting journey: grounding side effect.')
    // Select OUR vehicle by its id (option value), since the display label
    // (manufacturer+model) is not unique.
    await modal.locator('#vehicle').selectOption({ value: String(vehicle.id) })
    // The grounding control.
    await modal.locator('#equip_grounded').check()
    await expect(modal.locator('#equip_grounded')).toBeChecked()

    await modal.getByRole('button', { name: 'Report Incident' }).click()

    // Modal closes and our incident lands in the list.
    await expect(modal).toBeHidden({ timeout: 10_000 })
    const myRow = page.getByRole('row').filter({ hasText: title })
    await expect(myRow).toBeVisible({ timeout: 10_000 })

    // --- Step 3: assert the cross-cutting side effect END TO END ---
    // Navigate to the vehicle detail page and assert the status flipped from
    // active to maintenance, verified through the real UI/stack.
    await page.goto(`/fleet/vehicles/${vehicle.id}`)
    await expect(page.getByText(`S/N: ${serial}`)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('maintenance', { exact: true })).toBeVisible({ timeout: 10_000 })
  })
})
