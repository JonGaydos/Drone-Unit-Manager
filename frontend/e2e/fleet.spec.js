import { test, expect } from '@playwright/test'

// Fleet journey: add a vehicle and a battery through the real UI, confirm each
// lands in its tab's list, then open its detail page and assert the entered
// fields render. Runs as the default admin storageState. Admin qualifies as
// supervisor, so the "Add Vehicle" / "Add Battery" controls and the equipment
// modal are available. The suite shares one seeded DB across re-runs, so every
// entity is created with a unique, searchable serial and we assert only on OUR
// row (never on global counts).
//
// Real UI used (read from src/pages/FleetPage.jsx + VehicleDetailPage.jsx +
// BatteryDetailPage.jsx):
//   - Tabs are buttons: "Vehicles", "Batteries", "Controllers", "Docks",
//     "Sensors", "Attachments". Vehicles is the default tab.
//   - Add: "Add <Singular>" button (e.g. "Add Vehicle") opens a role="dialog"
//     Modal headed "Add Vehicle". Each field input has id="field-<key>".
//       Vehicle fields:  #field-serial_number, #field-manufacturer,
//                        #field-model, #field-nickname (+ acquired_date / status
//                        select / notes).
//       Battery fields:  #field-serial_number, #field-nickname,
//                        #field-manufacturer, #field-model,
//                        #field-vehicle_model (combobox), #field-cycle_count,
//                        #field-health_pct (+ purchase_date / status select).
//     Submit button text equals "Add Vehicle" / "Add Battery".
//   - List rows: the primary cell links to the detail page. Vehicle link text =
//     nickname || serial_number -> /fleet/vehicles/:id. Battery link text =
//     nickname || serial_number -> /fleet/batteries/:id.
//   - Vehicle detail header shows "S/N: <serial>" and a manufacturer+model
//     title. Battery detail header shows manufacturer, model and "S/N: <serial>".
//
// Search matches the visible columns (joined), so a unique serial/nickname
// filters the list down to exactly our row.

async function gotoFleet(page) {
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('link', { name: 'Fleet', exact: true }).click()
  await expect(page).toHaveURL(/\/fleet(?:$|[/?])/)
}

test.describe('fleet journey', () => {
  test('add a vehicle via the UI, find it in the list, open its detail page', async ({ page }) => {
    const stamp = Date.now()
    const serial = `E2E-VEH-${stamp}`
    const nickname = `E2E Fleet Drone ${stamp}`
    const manufacturer = 'Autel Robotics'
    const model = `EVO-${stamp}`

    await gotoFleet(page)
    // Vehicles is the default tab; the Add control reads "Add Vehicle".
    await page.getByRole('button', { name: 'Add Vehicle' }).click()

    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Add Vehicle' })).toBeVisible()
    await modal.locator('#field-serial_number').fill(serial)
    await modal.locator('#field-manufacturer').fill(manufacturer)
    await modal.locator('#field-model').fill(model)
    await modal.locator('#field-nickname').fill(nickname)
    await modal.getByRole('button', { name: 'Add Vehicle' }).click()

    // Modal closes and our row appears (its primary cell shows the nickname,
    // which links to the detail page).
    await expect(modal).toBeHidden({ timeout: 10_000 })
    const myRow = page.getByRole('row').filter({ hasText: serial })
    await expect(myRow).toBeVisible({ timeout: 10_000 })
    await expect(myRow).toContainText(nickname)
    await expect(myRow).toContainText(manufacturer)

    // Open its detail page; assert the serial / manufacturer / model render.
    await myRow.getByRole('link', { name: nickname }).click()
    await expect(page).toHaveURL(/\/fleet\/vehicles\/\d+/)
    await expect(page.getByText(`S/N: ${serial}`)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: new RegExp(model) })).toBeVisible()
    await expect(page.getByText(manufacturer, { exact: false }).first()).toBeVisible()
  })

  test('switch to the Batteries tab, add a battery, find it, open its detail page', async ({ page }) => {
    const stamp = Date.now()
    const serial = `E2E-BAT-${stamp}`
    const nickname = `E2E Fleet Battery ${stamp}`
    const manufacturer = 'DJI'
    const model = `TB60-${stamp}`

    await gotoFleet(page)
    // Switch tabs immediately. FleetPage.load() guards against stale responses,
    // so a still-in-flight vehicles load cannot clobber the batteries list even
    // if it resolves after the fast batteries load. The Add control + columns
    // follow the active tab config.
    await page.getByRole('button', { name: 'Batteries' }).click()
    await expect(page.getByPlaceholder('Search batteries...')).toBeVisible({ timeout: 10_000 })
    // Confirm the list now reflects the batteries endpoint (Serial column header
    // is unique to the batteries tab config) before asserting on our new row.
    await expect(page.getByRole('columnheader', { name: 'Serial', exact: true })).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: 'Add Battery' }).click()
    const modal = page.getByRole('dialog')
    await expect(modal.getByRole('heading', { name: 'Add Battery' })).toBeVisible()
    await modal.locator('#field-serial_number').fill(serial)
    await modal.locator('#field-nickname').fill(nickname)
    await modal.locator('#field-manufacturer').fill(manufacturer)
    await modal.locator('#field-model').fill(model)
    await modal.locator('#field-cycle_count').fill('12')
    await modal.locator('#field-health_pct').fill('95')
    await modal.getByRole('button', { name: 'Add Battery' }).click()

    // Modal closes and our battery row appears in the Batteries list.
    await expect(modal).toBeHidden({ timeout: 10_000 })
    const myRow = page.getByRole('row').filter({ hasText: serial })
    await expect(myRow).toBeVisible({ timeout: 10_000 })
    await expect(myRow).toContainText(nickname)
    await expect(myRow).toContainText(manufacturer)

    // Open its detail page; assert an entered field renders.
    await myRow.getByRole('link', { name: nickname }).click()
    await expect(page).toHaveURL(/\/fleet\/batteries\/\d+/)
    await expect(page.getByText(`S/N: ${serial}`)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: nickname })).toBeVisible()
  })
})
