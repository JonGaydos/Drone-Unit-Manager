import { chromium, request as playwrightRequest } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import {
  apiLogin, createUser, createVehicle, createPilotRecord,
  createFlight, createCertType, createPilotCertification,
} from './helpers/seed.js'

const APP = 'http://localhost:5173'
const ADMIN = { username: 'e2eadmin', password: 'E2eAdminPass1', display: 'E2E Admin', org: 'E2E Unit' }
const PILOT = { username: 'e2epilot', password: 'E2ePilotPass1' }

export default async function globalSetup() {
  mkdirSync('e2e/.auth', { recursive: true })
  const browser = await chromium.launch()

  // 1) Drive the real 3-step setup wizard to create the first admin. This IS
  //    the setup journey. Labels/buttons match frontend/src/pages/SetupPage.jsx.
  const page = await (await browser.newContext()).newPage()
  await page.goto(APP)

  // Step 1: Organization. "Continue" enables only once "Your Name" is filled.
  await page.getByLabel('Your Name').fill(ADMIN.display)
  await page.getByLabel('Organization Name').fill(ADMIN.org)
  await page.getByLabel('Email Address').fill('e2eadmin@example.com')
  await page.getByRole('button', { name: /Continue/ }).click()

  // Step 2: Create Admin Account.
  await page.getByLabel('Username').fill(ADMIN.username)
  await page.getByLabel('Password', { exact: true }).fill(ADMIN.password)
  await page.getByLabel('Confirm Password').fill(ADMIN.password)
  await page.getByRole('button', { name: 'Create Account & Start' }).click()

  // Step 3: optional setup ("Account created"). Skip everything and proceed.
  await page.getByRole('heading', { name: 'Account created' }).waitFor({ timeout: 15_000 })
  await page.getByRole('button', { name: /Go to Dashboard/ }).click()

  // Landed authenticated on the dashboard: the sidebar nav is present.
  await page.getByRole('link', { name: 'Dashboard', exact: true }).waitFor({ timeout: 15_000 })
  await page.context().storageState({ path: 'e2e/.auth/admin.json' })
  await page.close()

  // 2) Seed a pilot-role login + a small deterministic baseline via the API.
  const reqCtx = await playwrightRequest.newContext()
  const adminToken = await apiLogin(reqCtx, ADMIN.username, ADMIN.password)

  await createUser(reqCtx, adminToken, {
    username: PILOT.username, password: PILOT.password, role: 'pilot', display_name: 'E2E Pilot',
  })

  const vehicle = await createVehicle(reqCtx, adminToken, {
    serial_number: 'E2E-SEED-VEH-1', manufacturer: 'Skydio', model: 'X10', nickname: 'E2E Seed Drone',
  })
  await createVehicle(reqCtx, adminToken, {
    serial_number: 'E2E-SEED-VEH-2', manufacturer: 'DJI', model: 'Matrice 30', nickname: 'E2E Seed Drone 2',
  })
  const pilot = await createPilotRecord(reqCtx, adminToken, { first_name: 'E2E', last_name: 'Seedpilot' })
  await createPilotRecord(reqCtx, adminToken, { first_name: 'E2E', last_name: 'Seedpilot2' })

  await createFlight(reqCtx, adminToken, {
    pilot_id: pilot.id, vehicle_id: vehicle.id, date: '2026-06-10',
    duration_seconds: 600, purpose: 'Training', notes: 'E2E seed flight',
  })

  const certType = await createCertType(reqCtx, adminToken, {
    name: 'E2E Part 107', category: 'custom', has_expiration: true, renewal_period_months: 24,
  })
  // One expired cert so the compliance/currency view has a red status item.
  await createPilotCertification(reqCtx, adminToken, {
    pilot_id: pilot.id, certification_type_id: certType.id,
    status: 'complete', issue_date: '2020-01-01', expiration_date: '2022-01-01',
  })

  // 3) Save the pilot storageState by logging in through the real UI.
  const pilotPage = await (await browser.newContext()).newPage()
  await pilotPage.goto(`${APP}/login`)
  await pilotPage.getByLabel('Username').fill(PILOT.username)
  await pilotPage.getByLabel('Password', { exact: true }).fill(PILOT.password)
  await pilotPage.getByRole('button', { name: 'Sign In' }).click()
  await pilotPage.getByRole('link', { name: 'Dashboard', exact: true }).waitFor({ timeout: 15_000 })
  await pilotPage.context().storageState({ path: 'e2e/.auth/pilot.json' })
  await pilotPage.close()

  await reqCtx.dispose()
  await browser.close()
}
